"""
app/repositories/domestic_bond_rate_repository.py

Data access layer for KIS domestic bond interest rates.
All DB reads and writes go through this class.
"""
import logging
from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from app.models.domestic_bond_rate import DomesticBondRateModel
from app.schemas.domestic_bond_rate import DomesticBondRateRecord

logger = logging.getLogger(__name__)


class DomesticBondRateRepository:
    """Repository for the domestic_bond_rates table."""

    def upsert_rates(self, db: Session, data: list[DomesticBondRateRecord]) -> int:
        """
        Insert or update domestic bond rate rows.

        Matches existing rows on (source, market_div_code, screen_div_code,
        cls_code, rate_code, base_date). Updates rate_name, rate_value and
        fetched_at if a row already exists; inserts otherwise.

        Returns:
            Number of rows inserted or updated.
        """
        affected = 0
        for record in data:
            fetched_at = datetime.fromisoformat(record.fetched_at)

            existing = (
                db.query(DomesticBondRateModel)
                .filter_by(
                    source=record.source,
                    market_div_code=record.market_div_code,
                    screen_div_code=record.screen_div_code,
                    cls_code=record.cls_code,
                    rate_code=record.rate_code,
                    base_date=record.base_date,
                )
                .first()
            )
            if existing:
                existing.rate_name = record.rate_name
                existing.rate_value = record.rate_value
                existing.fetched_at = fetched_at
            else:
                db.add(
                    DomesticBondRateModel(
                        source=record.source,
                        market_div_code=record.market_div_code,
                        screen_div_code=record.screen_div_code,
                        cls_code=record.cls_code,
                        rate_code=record.rate_code,
                        rate_name=record.rate_name,
                        rate_value=record.rate_value,
                        base_date=record.base_date,
                        fetched_at=fetched_at,
                    )
                )
            affected += 1

        db.commit()
        logger.info("Upserted %d domestic bond rate rows.", affected)
        return affected

    def get_rates(
        self,
        db: Session,
        market_div_code: str,
        base_date: Optional[str] = None,
    ) -> list[DomesticBondRateModel]:
        """
        Return domestic bond rate rows for a given market_div_code, optionally
        filtered by base_date, ordered by base_date descending then rate_name.
        """
        query = db.query(DomesticBondRateModel).filter_by(market_div_code=market_div_code)
        if base_date is not None:
            query = query.filter_by(base_date=base_date)
        return query.order_by(
            DomesticBondRateModel.base_date.desc(),
            DomesticBondRateModel.rate_name.asc(),
        ).all()
