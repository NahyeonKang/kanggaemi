from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from decimal import Decimal

import holidays
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.domestic_derivative_master import DomesticDerivativeMasterModel
from app.repositories.active_contract_repository import ActiveContractRepository
from app.repositories.domestic_derivative_master_repository import DomesticDerivativeMasterRepository
from app.services.instrument_price_service import InstrumentPriceService


_EXPIRY_MONTH = re.compile(r"\b(20\d{4})\b")
_KR_HOLIDAYS = holidays.KR()


def resolve_domestic_contract(
    db: Session,
    *,
    as_of_date: str,
    product: str,
    underlying_cd: str,
    market_type: str,
    candidate_count: int,
    lookback_days: int,
    rollover_business_days: int,
) -> dict:
    effective_date = datetime.strptime(as_of_date, "%Y-%m-%d").date()
    cache = ActiveContractRepository()
    existing = cache.get_for_date(db, as_of_date, "domestic", product)
    master_updated_at = db.query(func.max(DomesticDerivativeMasterModel.updated_at)).scalar()
    if (
        existing is not None
        and (master_updated_at is None or master_updated_at <= existing.resolved_at)
    ):
        return _summary(existing, cached=True)

    candidates = _eligible_candidates(
        DomesticDerivativeMasterRepository().get_futures_candidates(
            db, underlying_cd=underlying_cd, market_type=market_type
        ),
        effective_date,
    )[:candidate_count]
    if not candidates:
        raise RuntimeError(f"no unexpired futures candidates for underlying={underlying_cd}")

    service = InstrumentPriceService()
    start = (effective_date - timedelta(days=lookback_days)).strftime("%Y%m%d")
    end = effective_date.strftime("%Y%m%d")
    start_iso = f"{start[:4]}-{start[4:6]}-{start[6:]}"
    end_iso = f"{end[:4]}-{end[4:6]}-{end[6:]}"
    volumes: dict[str, dict[str, Decimal]] = {}
    for candidate, _ in candidates:
        service.sync_chart(
            db,
            asset_class="future",
            entity_code=candidate.srs_cd,
            period="D",
            start_date=start,
            end_date=end,
            adj="0",
        )
        rows = service.get_ohlcv(
            db, "future", candidate.srs_cd, "D",
            start_iso, end_iso,
        )
        volumes[candidate.srs_cd] = {
            row.observation_date: row.volume
            for row in rows
            if row.volume is not None
        }

    common_dates = set.intersection(*(set(series) for series in volumes.values()))
    if not common_dates:
        raise RuntimeError("domestic futures candidates have no common volume date")
    reference_date = max(common_dates)
    winner, expiry = min(
        candidates,
        key=lambda item: (
            -volumes[item[0].srs_cd][reference_date],
            item[1],
        ),
    )
    winning_volume = volumes[winner.srs_cd][reference_date]

    previous = cache.get_latest_before(db, "domestic", product, as_of_date)
    reason = _rollover_reason(
        previous, winner.srs_cd, effective_date, rollover_business_days
    )
    row = cache.upsert_daily(
        db,
        as_of_date=as_of_date,
        market="domestic",
        product=product,
        contract_code=winner.srs_cd,
        exch_cd=None,
        master_product_code=underlying_cd,
        expiry_date=expiry.isoformat(),
        resolution_method="volume",
        reference_date=reference_date,
        reference_volume=winning_volume,
        rollover_reason=reason,
    )
    return _summary(row, cached=False)


def _eligible_candidates(
    rows: list[DomesticDerivativeMasterModel], effective_date: date
) -> list[tuple[DomesticDerivativeMasterModel, date]]:
    candidates = []
    for row in rows:
        expiry = _expiry_date(row.name)
        if expiry is not None and expiry >= effective_date:
            candidates.append((row, expiry))
    return sorted(candidates, key=lambda item: item[1])


def _expiry_date(name: str | None) -> date | None:
    match = _EXPIRY_MONTH.search(name or "")
    if not match:
        return None
    raw = match.group(1)
    year, month = int(raw[:4]), int(raw[4:])
    first = date(year, month, 1)
    first_thursday = first + timedelta(days=(3 - first.weekday()) % 7)
    return first_thursday + timedelta(days=7)


def _business_days_until(start: date, end: date) -> int:
    count = 0
    current = start
    while current < end:
        current += timedelta(days=1)
        if current.weekday() < 5 and current not in _KR_HOLIDAYS:
            count += 1
    return count


def _rollover_reason(previous, winner_code: str, effective_date: date, threshold: int) -> str:
    if previous is None:
        return "initial"
    if previous.contract_code == winner_code:
        return "unchanged"
    if previous.expiry_date:
        previous_expiry = datetime.strptime(previous.expiry_date, "%Y-%m-%d").date()
        if _business_days_until(effective_date, previous_expiry) <= threshold:
            return "expiry_window"
    return "volume_leader"


def _summary(row, *, cached: bool) -> dict:
    return {
        "market": row.market,
        "product": row.product,
        "contract_code": row.contract_code,
        "expiry_date": row.expiry_date,
        "as_of_date": row.as_of_date,
        "reference_date": row.reference_date,
        "reference_volume": row.reference_volume,
        "resolution_method": row.resolution_method,
        "rollover_reason": row.rollover_reason,
        "cached": cached,
    }
