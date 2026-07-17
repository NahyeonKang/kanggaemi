from __future__ import annotations

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.overseas_future_master import OverseasFutureMasterModel
from app.repositories.active_contract_repository import ActiveContractRepository
from app.repositories.overseas_future_master_repository import OverseasFutureMasterRepository


def resolve_overseas_contract(
    db: Session,
    *,
    as_of_date: str,
    product: str,
    product_code: str,
) -> dict:
    cache = ActiveContractRepository()
    existing = cache.get_for_date(db, as_of_date, "overseas", product)
    master_updated_at = db.query(func.max(OverseasFutureMasterModel.updated_at)).scalar()
    if (
        existing is not None
        and (master_updated_at is None or master_updated_at <= existing.resolved_at)
    ):
        return _summary(existing, cached=True)

    contract = OverseasFutureMasterRepository().resolve_active_contract(db, product_code)
    if contract is None:
        raise RuntimeError(
            f"no most-active/nearest outright contract for product_code={product_code}"
        )
    previous = cache.get_latest_before(db, "overseas", product, as_of_date)
    reason = (
        "initial"
        if previous is None
        else "flag_roll" if previous.contract_code != contract.srs_cd else "unchanged"
    )
    row = cache.upsert_daily(
        db,
        as_of_date=as_of_date,
        market="overseas",
        product=product,
        contract_code=contract.srs_cd,
        exch_cd=contract.exch_cd,
        master_product_code=product_code,
        expiry_date=None,
        resolution_method="master_flag",
        rollover_reason=reason,
    )
    return _summary(row, cached=False)


def _summary(row, *, cached: bool) -> dict:
    return {
        "market": row.market,
        "product": row.product,
        "contract_code": row.contract_code,
        "exch_cd": row.exch_cd,
        "as_of_date": row.as_of_date,
        "resolution_method": row.resolution_method,
        "rollover_reason": row.rollover_reason,
        "cached": cached,
    }
