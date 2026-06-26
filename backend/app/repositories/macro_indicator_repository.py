"""
app/repositories/macro_indicator_repository.py

매크로 관측 데이터 접근 계층 (macro_observation).
"""
import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from sqlalchemy.orm import Session

from app.models.macro_indicator import MacroObservationModel

logger = logging.getLogger(__name__)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class MacroIndicatorRepository:
    """Repository for the macro_observation table."""

    def upsert_observations(
        self,
        db: Session,
        source: str,
        series_id: str,
        resolution: str,
        rows: list[tuple[str, Optional[Decimal]]],
    ) -> int:
        """rows: [(observation_date, value)]. 값 변동/신규일 때만 카운트."""
        now = _utcnow()
        affected = 0
        for observation_date, value in rows:
            existing = (
                db.query(MacroObservationModel)
                .filter_by(
                    source=source,
                    series_id=series_id,
                    resolution=resolution,
                    observation_date=observation_date,
                )
                .first()
            )
            if existing:
                if existing.value != value:
                    existing.value = value
                    existing.ingested_at = now
                    affected += 1
            else:
                db.add(
                    MacroObservationModel(
                        source=source,
                        series_id=series_id,
                        resolution=resolution,
                        observation_date=observation_date,
                        value=value,
                        ingested_at=now,
                    )
                )
                affected += 1

        db.commit()
        logger.info(
            "Upserted %d macro obs for %s (%s).", affected, series_id, resolution
        )
        return affected

    def get_observations(
        self,
        db: Session,
        series_id: str,
        start_date: str,
        end_date: str,
        resolution: str = "D",
    ) -> list[MacroObservationModel]:
        return (
            db.query(MacroObservationModel)
            .filter(
                MacroObservationModel.series_id == series_id,
                MacroObservationModel.resolution == resolution,
                MacroObservationModel.observation_date >= start_date,
                MacroObservationModel.observation_date <= end_date,
            )
            .order_by(MacroObservationModel.observation_date.asc())
            .all()
        )