"""
app/repositories/yield_rate_repository.py

금리 도메인 데이터 접근 계층.
  - yield_observation : 값 변동 시에만 갱신.
  - yield_intraday_snapshot : append-only, as-of 조회.
"""
import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from sqlalchemy.orm import Session

from app.models.yield_rate import YieldObservationModel, YieldIntradaySnapshotModel
from app.schemas.yield_rate import YieldSnapshotRecord

logger = logging.getLogger(__name__)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class YieldRateRepository:
    """Repository for yield_observation and yield_intraday_snapshot tables."""

    # ── 관측 시계열 (daily/monthly) ──────────────────────────
    def upsert_observations(
        self,
        db: Session,
        source: str,
        country: str,
        tenor: str,
        resolution: str,
        rows: list[tuple[str, Optional[Decimal]]],
    ) -> int:
        """rows: [(observation_date, close)]. 값 변동/신규일 때만 카운트."""
        now = _utcnow()
        affected = 0
        for observation_date, close in rows:
            existing = (
                db.query(YieldObservationModel)
                .filter_by(
                    source=source,
                    country=country,
                    tenor=tenor,
                    resolution=resolution,
                    observation_date=observation_date,
                )
                .first()
            )
            if existing:
                if existing.close != close:
                    existing.close = close
                    existing.ingested_at = now
                    affected += 1
            else:
                db.add(
                    YieldObservationModel(
                        source=source,
                        country=country,
                        tenor=tenor,
                        resolution=resolution,
                        observation_date=observation_date,
                        close=close,
                        ingested_at=now,
                    )
                )
                affected += 1

        db.commit()
        logger.info(
            "Upserted %d yield obs for %s/%s (%s).",
            affected, country, tenor, resolution,
        )
        return affected

    def get_observations(
        self,
        db: Session,
        country: str,
        tenor: str,
        resolution: str = "D",
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> list[YieldObservationModel]:
        query = db.query(YieldObservationModel).filter(
            YieldObservationModel.country == country,
            YieldObservationModel.tenor == tenor,
            YieldObservationModel.resolution == resolution,
        )
        if start_date is not None:
            query = query.filter(YieldObservationModel.observation_date >= start_date)
        if end_date is not None:
            query = query.filter(YieldObservationModel.observation_date <= end_date)
        return query.order_by(YieldObservationModel.observation_date.asc()).all()

    # ── 장중 스냅샷 (append-only) ────────────────────────────
    def insert_snapshot(self, db: Session, rec: YieldSnapshotRecord) -> int:
        """fetch마다 1행 append. 동일 (source, country, tenor, observed_at) 멱등 skip."""
        exists = (
            db.query(YieldIntradaySnapshotModel.id)
            .filter_by(
                source=rec.source,
                country=rec.country,
                tenor=rec.tenor,
                observed_at=rec.observed_at,
            )
            .first()
        )
        if exists:
            return 0

        db.add(
            YieldIntradaySnapshotModel(
                source=rec.source,
                country=rec.country,
                tenor=rec.tenor,
                observed_at=rec.observed_at,
                current_rate=rec.current_rate,
                prdy_vrss_sign=rec.prdy_vrss_sign,
                prdy_vrss=rec.prdy_vrss,
                prdy_ctrt=rec.prdy_ctrt,
                base_date=rec.base_date,
                ingested_at=_utcnow(),
            )
        )
        db.commit()
        return 1

    def get_latest_snapshot(
        self, db: Session, country: str, tenor: str
    ) -> Optional[YieldIntradaySnapshotModel]:
        return (
            db.query(YieldIntradaySnapshotModel)
            .filter_by(country=country, tenor=tenor)
            .order_by(YieldIntradaySnapshotModel.observed_at.desc())
            .first()
        )

    def get_snapshot_asof(
        self, db: Session, country: str, tenor: str, as_of: datetime
    ) -> Optional[YieldIntradaySnapshotModel]:
        """as_of 시점 point-in-time 스냅샷. as_of는 tz-aware로 전달."""
        return (
            db.query(YieldIntradaySnapshotModel)
            .filter_by(country=country, tenor=tenor)
            .filter(YieldIntradaySnapshotModel.observed_at <= as_of)
            .order_by(YieldIntradaySnapshotModel.observed_at.desc())
            .first()
        )

    def list_latest_snapshots(
        self, db: Session, country: Optional[str] = None
    ) -> list[YieldIntradaySnapshotModel]:
        """(country, tenor)별 최신 스냅샷. Postgres DISTINCT ON."""
        query = db.query(YieldIntradaySnapshotModel)
        if country is not None:
            query = query.filter_by(country=country)
        return (
            query.distinct(
                YieldIntradaySnapshotModel.country,
                YieldIntradaySnapshotModel.tenor,
            )
            .order_by(
                YieldIntradaySnapshotModel.country.asc(),
                YieldIntradaySnapshotModel.tenor.asc(),
                YieldIntradaySnapshotModel.observed_at.desc(),
            )
            .all()
        )