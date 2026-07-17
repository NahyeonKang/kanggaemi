from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, time, timedelta
from decimal import Decimal
from typing import Callable
from zoneinfo import ZoneInfo

from app.agent.catalog import load_yaml
from app.agent.contracts import Evidence, FactorFeature, SelectedFactor
from app.batch.dates import latest_completed_kr_business_date
from app.batch.kis_token_throttle import KisTokenThrottle
from app.db.session import SessionLocal
from app.repositories.active_contract_repository import ActiveContractRepository
from app.repositories.instrument_price_repository import InstrumentPriceRepository
from app.repositories.investor_flow_repository import InvestorFlowRepository
from app.repositories.program_trade_repository import ProgramTradeRepository
from app.scrapers.kis.kis_auth import KISAuthClient
from app.services.instrument_price_service import InstrumentPriceService
from app.services.investor_flow_service import InvestorFlowService
from app.services.program_trade_service import ProgramTradeService


@dataclass(frozen=True)
class SeriesPoint:
    observation_date: str
    value: float
    source: str
    entity_code: str | None = None


class FetchOnMissCoordinator:
    def __init__(self) -> None:
        self._fetched: set[tuple[str, str]] = set()

    def fetch_stock_bundle(self, ticker: str, as_of_date: str) -> list[str]:
        key = (ticker, as_of_date)
        if key in self._fetched:
            return []
        self._fetched.add(key)
        KisTokenThrottle().reserve("agent-fetch-on-miss", 65)
        auth = KISAuthClient()
        price = InstrumentPriceService()
        investor = InvestorFlowService()
        program = ProgramTradeService()
        price._scraper._auth = auth
        investor._scraper._auth = auth
        program._scraper._auth = auth
        end = as_of_date.replace("-", "")
        start = (datetime.strptime(end, "%Y%m%d") - timedelta(days=365)).strftime("%Y%m%d")
        completed = latest_completed_kr_business_date()
        flow_date = min(end, completed)
        errors: list[str] = []
        with SessionLocal() as db:
            operations: list[tuple[str, Callable[[], object]]] = [
                ("price", lambda: price.sync_chart(
                    db, asset_class="stock", entity_code=ticker, period="D",
                    start_date=start, end_date=end, adj="0",
                )),
                ("investor_flow", lambda: investor.sync_stock_daily(db, ticker, flow_date)),
                ("program_trade", lambda: program.sync_stock_daily(db, ticker, flow_date)),
            ]
            for domain, operation in operations:
                try:
                    operation()
                except Exception as exc:  # each existing sync remains independently useful
                    errors.append(f"{domain}: {type(exc).__name__}: {exc}")
        return errors


class FeatureEngine:
    """Point-in-time feature reader driven by data_specs and factor transforms."""

    def __init__(self, fetcher: FetchOnMissCoordinator | None = None) -> None:
        self.fetcher = fetcher or FetchOnMissCoordinator()
        self.data_specs = {
            item["data_spec_id"]: item for item in load_yaml("data_specs.yaml")["data_specs"]
        }
        self.investor_repo = InvestorFlowRepository()
        self.program_repo = ProgramTradeRepository()
        self.active_contract_repo = ActiveContractRepository()
        self.price_repo = InstrumentPriceRepository()

    def compute_factor(
        self, factor: SelectedFactor, classification: dict, as_of_date: str
    ) -> FactorFeature:
        data_spec_id = self._effective_data_spec(factor.data_spec_id, classification)
        spec = self.data_specs.get(data_spec_id)
        if spec is None or spec.get("status") != "active":
            return self._missing(factor, f"inactive or unknown data_spec: {data_spec_id}")
        try:
            selector = _selector(factor.factor_id)
        except ValueError as exc:
            return self._missing(factor, str(exc))
        window = _window_size(factor.transform.get("window"))
        lookback_days = (
            400 if factor.transform.get("method") == "yoy_growth"
            else max(40, window * 3)
        )
        start_date = (
            datetime.strptime(as_of_date, "%Y-%m-%d") - timedelta(days=lookback_days)
        ).strftime("%Y-%m-%d")
        points = self._read_points(
            data_spec_id, classification, selector, start_date, as_of_date
        )
        fetch_errors: list[str] = []
        required = _required_points(factor.transform.get("method", "level"), window)
        if len(points) < required and classification["asset_class"] == "kr_equity":
            fetch_errors = self.fetcher.fetch_stock_bundle(
                classification["asset_code"], as_of_date
            )
            points = self._read_points(
                data_spec_id, classification, selector, start_date, as_of_date
            )
        if len(points) < required:
            reason = f"insufficient as_of history: required={required}, actual={len(points)}"
            if fetch_errors:
                reason += "; fetch_on_miss=" + " | ".join(fetch_errors)
            return self._missing(factor, reason)
        transformed = apply_transform(points, factor.transform)
        if transformed is None or not math.isfinite(transformed):
            return self._missing(factor, "transform produced no finite value")
        latest = points[-1]
        field = selector["field"]
        unit = _field_unit(spec, field, factor)
        evidence = Evidence(
            data_spec_id=data_spec_id,
            source=latest.source,
            entity_code=latest.entity_code or classification["asset_code"],
            field=field,
            value=transformed,
            unit=unit,
            observation_date=latest.observation_date,
            as_of_date=as_of_date,
            transform=factor.transform,
            is_estimated=bool(spec["data_contract"].get("is_estimated", False)),
            caveats=list(spec.get("caveats") or []),
        )
        return FactorFeature(
            factor_id=factor.factor_id,
            factor_name=factor.factor_name,
            signal=_signal(transformed),
            strength=min(1.0, abs(transformed) / (abs(transformed) + 1.0)),
            evidence=evidence,
            caveat=factor.caveats,
        )

    def _read_points(
        self, data_spec_id: str, asset: dict, selector: dict,
        start_date: str, as_of_date: str,
    ) -> list[SeriesPoint]:
        with SessionLocal() as db:
            if data_spec_id == "DS_KR_EQUITY_INVESTOR_FLOW":
                rows = self.investor_repo.get_flows(
                    db, scope="stock", entity_code=asset["asset_code"],
                    start_date=start_date, end_date=as_of_date,
                    investor_type=selector["investor_type"], market=None,
                )
            elif data_spec_id == "DS_KR_MARKET_INVESTOR_FLOW":
                entity_code = "0001"
                rows = self.investor_repo.get_flows(
                    db, scope="market", entity_code=entity_code,
                    start_date=start_date, end_date=as_of_date,
                    investor_type=selector["investor_type"], market=asset["market"],
                )
            elif data_spec_id == "DS_KR_EQUITY_PROGRAM_TRADING":
                rows = self.program_repo.get_series(
                    db, scope="stock", entity_code=asset["asset_code"],
                    start_date=start_date, end_date=as_of_date,
                    trade_class="whol", account_type="smtn",
                )
            elif data_spec_id == "DS_KR_MARKET_PROGRAM_TRADING":
                rows = self.program_repo.get_series(
                    db, scope="market", entity_code=asset["market"],
                    start_date=start_date, end_date=as_of_date,
                    trade_class="whol", account_type="smtn",
                )
            elif data_spec_id == "DS_KR_INDEX_FUTURES_BASIS":
                # The configured domestic futures product represents KOSPI200/KOSPI.
                # Other indices intentionally report missing data until a grounded
                # product mapping is added to the contracts/configuration.
                if asset.get("asset_code") != "0001" and asset.get("market") != "KOSPI":
                    return []
                contracts = self.active_contract_repo.get_history_for_window(
                    db, market="domestic", product="KOSPI200",
                    start_date=start_date, end_date=as_of_date,
                )
                if not contracts:
                    return []
                kst = ZoneInfo("Asia/Seoul")
                start_at = datetime.combine(
                    datetime.strptime(start_date, "%Y-%m-%d").date(), time.min, tzinfo=kst
                )
                end_at = datetime.combine(
                    datetime.strptime(as_of_date, "%Y-%m-%d").date(), time.max, tzinfo=kst
                )
                snapshots = []
                for contract_code in {row.contract_code for row in contracts}:
                    snapshots.extend(self.price_repo.get_derivative_history_asof(
                        db, contract_code, start_at, end_at,
                    ))
                rows = [
                    row for row in snapshots
                    if _contract_for_date(contracts, _kst_date(row.observed_at))
                    == row.entity_code
                ]
                rows.sort(key=lambda row: row.observed_at)
            else:
                return []
        points = []
        for row in rows:
            raw = getattr(row, selector["field"], None)
            if raw is not None:
                observed_at = getattr(row, "observed_at", None)
                observation_date = (
                    _kst_date(observed_at) if observed_at is not None
                    else row.observation_date
                )
                points.append(SeriesPoint(
                    observation_date=observation_date,
                    value=float(Decimal(raw)), source=row.source,
                    entity_code=getattr(row, "entity_code", None),
                ))
        if data_spec_id == "DS_KR_INDEX_FUTURES_BASIS":
            # Daily factors consume the last observable snapshot of each KST day.
            points = list({point.observation_date: point for point in points}.values())
        return points

    @staticmethod
    def _effective_data_spec(data_spec_id: str, asset: dict) -> str:
        if asset["asset_class"] == "kr_equity":
            return {
                "DS_KR_MARKET_INVESTOR_FLOW": "DS_KR_EQUITY_INVESTOR_FLOW",
                "DS_KR_MARKET_PROGRAM_TRADING": "DS_KR_EQUITY_PROGRAM_TRADING",
            }.get(data_spec_id, data_spec_id)
        return data_spec_id

    @staticmethod
    def _missing(factor: SelectedFactor, reason: str) -> FactorFeature:
        return FactorFeature(
            factor_id=factor.factor_id, factor_name=factor.factor_name,
            signal="unknown", strength=0, missing_reason=reason,
            caveat=factor.caveats,
        )


def apply_transform(points: list[SeriesPoint], transform: dict) -> float | None:
    method = transform.get("method", "level")
    window = _window_size(transform.get("window"))
    values = [point.value for point in points]
    if not values:
        return None
    if method == "level":
        return values[-1]
    if method == "rolling_sum":
        return sum(values[-window:])
    if method == "z_score":
        sample = values[-window:]
        mean = sum(sample) / len(sample)
        variance = sum((value - mean) ** 2 for value in sample) / len(sample)
        return 0.0 if variance == 0 else (sample[-1] - mean) / math.sqrt(variance)
    if method == "pct_change":
        base = values[-window] if len(values) >= window else values[0]
        return None if base == 0 else (values[-1] / base - 1.0) * 100.0
    if method == "level_and_delta":
        base = values[-window] if len(values) >= window else values[0]
        return values[-1] - base
    if method == "yoy_growth":
        latest_date = datetime.strptime(points[-1].observation_date, "%Y-%m-%d")
        cutoff = (latest_date - timedelta(days=365)).strftime("%Y-%m-%d")
        prior = next((point.value for point in reversed(points) if point.observation_date <= cutoff), None)
        return None if prior in (None, 0) else (values[-1] / prior - 1.0) * 100.0
    raise ValueError(f"unsupported transform method: {method}")


def _selector(factor_id: str) -> dict:
    values = {
        "FLOW_FOREIGN_SPOT": {"field": "net_amount", "investor_type": "frgn"},
        "FLOW_INSTITUTION_SPOT": {"field": "net_amount", "investor_type": "orgn"},
        "FLOW_INDIVIDUAL_SPOT": {"field": "net_amount", "investor_type": "prsn"},
        "PROGRAM_NET": {"field": "net_amount"},
        "FUTURES_OI": {"field": "open_interest"},
        "FUTURES_BASIS": {"field": "basis"},
        "FUTURES_BASIS_DISPARITY": {"field": "disparity"},
    }
    if factor_id not in values:
        raise ValueError(f"flow feature adapter missing for factor: {factor_id}")
    return values[factor_id]


def _window_size(value: str | None) -> int:
    if not value:
        return 1
    digits = "".join(character for character in str(value) if character.isdigit())
    return max(1, int(digits or "1"))


def _required_points(method: str, window: int) -> int:
    if method == "yoy_growth":
        return 2
    if method in {"rolling_sum", "z_score", "pct_change", "level_and_delta"}:
        return max(2, window)
    return 1


def _field_unit(spec: dict, field: str, factor: SelectedFactor) -> str:
    unit = spec["data_contract"].get("unit", factor.model_dump().get("unit", "unknown"))
    return str(unit.get(field, "unknown") if isinstance(unit, dict) else unit)


def _signal(value: float) -> str:
    if value > 0:
        return "positive"
    if value < 0:
        return "negative"
    return "neutral"


def _kst_date(value: datetime) -> str:
    if value.tzinfo is None:
        # PostgreSQL returns aware values for this column. Treat a naive value as
        # already-local only for lightweight SQLite/test compatibility.
        return value.date().isoformat()
    return value.astimezone(ZoneInfo("Asia/Seoul")).date().isoformat()


def _contract_for_date(contracts: list, observation_date: str) -> str | None:
    eligible = [row for row in contracts if row.as_of_date <= observation_date]
    return eligible[-1].contract_code if eligible else None
