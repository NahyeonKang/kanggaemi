"""
app/repositories/bok_bond_rate_repository.py

Data access layer for BOK ECOS historical bond rates.
All DB reads and writes go through this class.
"""
import logging
from datetime import datetime
from typing import Optional

from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from app.models.bok_bond_rate import BOKBondRateModel
from app.schemas.bok_bond_rate import BOKBondRateData

logger = logging.getLogger(__name__)


class BOKBondRateRepository:
    """Repository for the bok_bond_rates table."""

    def upsert_rates(self, db: Session, data: BOKBondRateData) -> int:
        """
        Insert or update bond rate observations from a BOKBondRateData result.

        Matches existing rows on (source, item_code, observation_date).
        Updates item_name, value and fetched_at if a row already exists;
        inserts otherwise.

        Returns:
            Number of rows inserted or updated.
        """
        fetched_at = datetime.fromisoformat(data.fetched_at)

        affected = 0
        for item in data.items:
            stmt = sqlite_insert(BOKBondRateModel).values(
                source=data.source,
                item_code=data.item_code,
                item_name=item.item_name,
                observation_date=item.observation_date,
                value=item.value,
                fetched_at=fetched_at,
            )
            stmt = stmt.on_conflict_do_update(
                index_elements=["source", "item_code", "observation_date"],
                set_={
                    "item_name": stmt.excluded.item_name,
                    "value": stmt.excluded.value,
                    "fetched_at": stmt.excluded.fetched_at,
                },
            )
            db.execute(stmt)
            affected += 1

        db.commit()
        logger.info("Upserted %d BOK bond rate rows for %s.", affected, data.item_code)
        return affected

    def get_rates(
        self,
        db: Session,
        item_code: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> list[BOKBondRateModel]:
        """
        Return bond rate rows for a given item_code, optionally filtered by
        an observation_date range, ordered by observation_date ascending.

        Args:
            db: SQLAlchemy session.
            item_code: ECOS item code (e.g. "010210000").
            start_date: Start date inclusive, YYYY-MM-DD.
            end_date: End date inclusive, YYYY-MM-DD.
        """
        query = db.query(BOKBondRateModel).filter(BOKBondRateModel.item_code == item_code)
        if start_date is not None:
            query = query.filter(BOKBondRateModel.observation_date >= start_date)
        if end_date is not None:
            query = query.filter(BOKBondRateModel.observation_date <= end_date)
        return query.order_by(BOKBondRateModel.observation_date.asc()).all()
