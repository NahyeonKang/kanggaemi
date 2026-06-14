"""
app/repositories/yield_rate_repository.py

Data access layer for the yield domain (yield_daily, yield_snapshot tables).
All DB reads and writes go through this class.
"""
import logging
from datetime import datetime
from typing import Optional

from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from app.models.yield_rate import YieldDailyModel, YieldSnapshotModel
from app.schemas.yield_rate import YieldSnapshotRecord

logger = logging.getLogger(__name__)


class YieldRateRepository:
    """Repository for the yield_daily and yield_snapshot tables."""

    def upsert_daily(
        self,
        db: Session,
        country: str,
        tenor: str,
        source: str,
        rows: list[tuple[str, Optional[float]]],
    ) -> int:
        """
        Insert or update daily close yields for a (country, tenor).

        Matches existing rows on (country, tenor, d). Updates close and
        source if a row already exists; inserts otherwise.

        Args:
            rows: list of (observation_date, close) tuples.

        Returns:
            Number of rows inserted or updated.
        """
        affected = 0
        for observation_date, close in rows:
            stmt = sqlite_insert(YieldDailyModel).values(
                country=country,
                tenor=tenor,
                d=observation_date,
                close=close,
                source=source,
            )
            stmt = stmt.on_conflict_do_update(
                index_elements=["country", "tenor", "d"],
                set_={
                    "close": stmt.excluded.close,
                    "source": stmt.excluded.source,
                },
            )
            db.execute(stmt)
            affected += 1

        db.commit()
        logger.info("Upserted %d yield_daily rows for %s/%s.", affected, country, tenor)
        return affected

    def get_daily(
        self,
        db: Session,
        country: str,
        tenor: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> list[YieldDailyModel]:
        """
        Return daily yield rows for a (country, tenor), optionally filtered
        by a date range, ordered by date ascending.
        """
        query = db.query(YieldDailyModel).filter(
            YieldDailyModel.country == country,
            YieldDailyModel.tenor == tenor,
        )
        if start_date is not None:
            query = query.filter(YieldDailyModel.d >= start_date)
        if end_date is not None:
            query = query.filter(YieldDailyModel.d <= end_date)
        return query.order_by(YieldDailyModel.d.asc()).all()

    def upsert_snapshot(self, db: Session, snapshot: YieldSnapshotRecord) -> int:
        """
        Insert or update the latest snapshot for a (country, tenor).

        Matches the existing row on (country, tenor) and updates all value
        columns if it exists; inserts otherwise.

        Returns:
            1 (number of rows affected).
        """
        fetched_at = datetime.fromisoformat(snapshot.fetched_at)

        stmt = sqlite_insert(YieldSnapshotModel).values(
            country=snapshot.country,
            tenor=snapshot.tenor,
            current_rate=snapshot.current_rate,
            prdy_vrss_sign=snapshot.prdy_vrss_sign,
            prdy_vrss=snapshot.prdy_vrss,
            prdy_ctrt=snapshot.prdy_ctrt,
            base_date=snapshot.base_date,
            source=snapshot.source,
            fetched_at=fetched_at,
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=["country", "tenor"],
            set_={
                "current_rate": stmt.excluded.current_rate,
                "prdy_vrss_sign": stmt.excluded.prdy_vrss_sign,
                "prdy_vrss": stmt.excluded.prdy_vrss,
                "prdy_ctrt": stmt.excluded.prdy_ctrt,
                "base_date": stmt.excluded.base_date,
                "source": stmt.excluded.source,
                "fetched_at": stmt.excluded.fetched_at,
            },
        )
        db.execute(stmt)
        db.commit()
        logger.info("Upserted yield_snapshot row for %s/%s.", snapshot.country, snapshot.tenor)
        return 1

    def get_snapshot(self, db: Session, country: str, tenor: str) -> Optional[YieldSnapshotModel]:
        """Return the latest snapshot for a (country, tenor), or None if absent."""
        return (
            db.query(YieldSnapshotModel)
            .filter_by(country=country, tenor=tenor)
            .first()
        )

    def list_snapshots(self, db: Session, country: Optional[str] = None) -> list[YieldSnapshotModel]:
        """Return all latest snapshots, optionally filtered by country."""
        query = db.query(YieldSnapshotModel)
        if country is not None:
            query = query.filter_by(country=country)
        return query.order_by(
            YieldSnapshotModel.country.asc(),
            YieldSnapshotModel.tenor.asc(),
        ).all()
