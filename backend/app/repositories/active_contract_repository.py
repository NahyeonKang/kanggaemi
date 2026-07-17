from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy.orm import Session

from app.models.active_contract import ActiveContractModel


class ActiveContractRepository:
    def get_for_date(
        self, db: Session, as_of_date: str, market: str, product: str
    ) -> ActiveContractModel | None:
        return (
            db.query(ActiveContractModel)
            .filter_by(as_of_date=as_of_date, market=market, product=product)
            .first()
        )

    def get_latest(
        self, db: Session, market: str, product: str
    ) -> ActiveContractModel | None:
        return (
            db.query(ActiveContractModel)
            .filter_by(market=market, product=product)
            .order_by(ActiveContractModel.as_of_date.desc())
            .first()
        )

    def get_latest_before(
        self, db: Session, market: str, product: str, as_of_date: str
    ) -> ActiveContractModel | None:
        return (
            db.query(ActiveContractModel)
            .filter_by(market=market, product=product)
            .filter(ActiveContractModel.as_of_date < as_of_date)
            .order_by(ActiveContractModel.as_of_date.desc())
            .first()
        )

    def get_latest_on_or_before(
        self, db: Session, market: str, product: str, as_of_date: str
    ) -> ActiveContractModel | None:
        """Return the contract known on ``as_of_date`` without looking ahead."""
        return (
            db.query(ActiveContractModel)
            .filter_by(market=market, product=product)
            .filter(ActiveContractModel.as_of_date <= as_of_date)
            .order_by(ActiveContractModel.as_of_date.desc())
            .first()
        )

    def get_history_for_window(
        self, db: Session, market: str, product: str,
        start_date: str, end_date: str,
    ) -> list[ActiveContractModel]:
        """Return window changes plus the contract already active at its start."""
        seed = self.get_latest_on_or_before(db, market, product, start_date)
        rows = (
            db.query(ActiveContractModel)
            .filter_by(market=market, product=product)
            .filter(
                ActiveContractModel.as_of_date >= start_date,
                ActiveContractModel.as_of_date <= end_date,
            )
            .order_by(ActiveContractModel.as_of_date.asc())
            .all()
        )
        if seed is not None and (
            not rows or seed.as_of_date < rows[0].as_of_date
        ):
            rows.insert(0, seed)
        return rows

    def upsert_daily(
        self,
        db: Session,
        *,
        as_of_date: str,
        market: str,
        product: str,
        contract_code: str,
        exch_cd: str | None,
        master_product_code: str | None,
        expiry_date: str | None,
        resolution_method: str,
        reference_date: str | None = None,
        reference_volume: Decimal | None = None,
        rollover_reason: str | None = None,
    ) -> ActiveContractModel:
        row = self.get_for_date(db, as_of_date, market, product)
        values = {
            "contract_code": contract_code,
            "exch_cd": exch_cd,
            "master_product_code": master_product_code,
            "expiry_date": expiry_date,
            "resolution_method": resolution_method,
            "reference_date": reference_date,
            "reference_volume": reference_volume,
            "rollover_reason": rollover_reason,
            "resolved_at": datetime.now(timezone.utc),
        }
        if row is None:
            row = ActiveContractModel(
                as_of_date=as_of_date, market=market, product=product, **values
            )
            db.add(row)
        else:
            for key, value in values.items():
                setattr(row, key, value)
        db.commit()
        db.refresh(row)
        return row
