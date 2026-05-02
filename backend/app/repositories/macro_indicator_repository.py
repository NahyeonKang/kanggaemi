"""
app/repositories/macro_indicator_repository.py

Data access layer for macro indicator observations.
All DB reads and writes go through this class.
"""
import logging
from datetime import datetime

from sqlalchemy.orm import Session

from app.models.macro_indicator import MacroIndicatorObservationModel
from app.schemas.macro_indicator import FredSeriesData

logger = logging.getLogger(__name__)


class MacroIndicatorRepository:
    """Repository for the macro_indicator_observations table."""

    def upsert_series_data(self, db: Session, data: FredSeriesData) -> int:
        """
        Insert or update observations from a FredSeriesData result.

        Matches existing rows on (source, series_id, observation_date).
        Updates value and fetched_at if a row already exists; inserts otherwise.

        Returns:
            Number of rows inserted or updated.
        """
        source    = data.source
        series_id = data.series_id

        affected = 0
        for obs in data.observations:
            fetched_at = datetime.fromisoformat(obs.fetched_at)

            existing = (
                db.query(MacroIndicatorObservationModel)
                .filter_by(
                    source=source,
                    series_id=series_id,
                    observation_date=obs.observation_date,
                )
                .first()
            )
            if existing:
                existing.value     = obs.value
                existing.fetched_at = fetched_at
            else:
                db.add(
                    MacroIndicatorObservationModel(
                        source=source,
                        series_id=series_id,
                        observation_date=obs.observation_date,
                        value=obs.value,
                        fetched_at=fetched_at,
                    )
                )
            affected += 1

        db.commit()
        logger.info("Upserted %d observations for %s.", affected, series_id)
        return affected

    def get_series(
        self,
        db: Session,
        series_id: str,
        start_date: str,
        end_date: str,
    ) -> list[MacroIndicatorObservationModel]:
        """
        Return observations for a given series within a date range,
        ordered by observation_date ascending.

        Args:
            db: SQLAlchemy session.
            series_id: FRED series identifier (e.g. "DGS10").
            start_date: Start date inclusive, YYYY-MM-DD.
            end_date: End date inclusive, YYYY-MM-DD.
        """
        return (
            db.query(MacroIndicatorObservationModel)
            .filter(
                MacroIndicatorObservationModel.series_id == series_id,
                MacroIndicatorObservationModel.observation_date >= start_date,
                MacroIndicatorObservationModel.observation_date <= end_date,
            )
            .order_by(MacroIndicatorObservationModel.observation_date.asc())
            .all()
        )
