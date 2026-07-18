"""
app/repositories/exchange_rate_repository.py

환율 데이터 접근 계층.
"""
import logging
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.exchange_rate import (
    ExchangeRateIntradaySnapshotModel,
    ExchangeRateDailyModel,
)
from app.schemas.exchange_rate import (
    KBUsdKrwIntradaySummary,
    KBUsdKrwDailySeries,
)

logger = logging.getLogger(__name__)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ExchangeRateRepository:
    """Repository for exchange rate snapshot and daily tables."""

    # ── 장중 스냅샷 (append-only) ─────────────────────────────
    def insert_snapshot(self, db: Session, data: KBUsdKrwIntradaySummary) -> int:
        """
        fetch마다 1행 append. 같은 (source, 통화쌍, target_date, observed_at) 재수집 skip. 
        return: 신규 삽입 행 수(0 또는 1).

        NOTE(운영): 단일 writer 가정의 check-then-insert. 동시 writer라면
        Postgres ON CONFLICT (uq_fx_intraday_snapshot) DO NOTHING 권장.
        """
        exists = (
            db.query(ExchangeRateIntradaySnapshotModel.id)
            .filter_by(
                source=data.source,
                base_ccy=data.base_ccy,
                quote_ccy=data.quote_ccy,
                target_date=data.target_date,
                observed_at=data.observed_at,
            )
            .first()
        )
        if exists:
            logger.info(
                "Snapshot exists for %s/%s %s @ %s, skipping.",
                data.base_ccy, data.quote_ccy, data.target_date, data.observed_at,
            )
            return 0

        db.add(
            ExchangeRateIntradaySnapshotModel(
                source=data.source,
                base_ccy=data.base_ccy,
                quote_ccy=data.quote_ccy,
                target_date=data.target_date,
                observed_at=data.observed_at,
                first_rate=data.first_rate,
                last_rate=data.last_rate,
                daily_low=data.daily_low,
                daily_high=data.daily_high,
                daily_avg=data.daily_avg,
                ingested_at=_utcnow(),
            )
        )
        db.commit()
        logger.info(
            "Inserted snapshot for %s/%s %s @ %s.",
            data.base_ccy, data.quote_ccy, data.target_date, data.observed_at,
        )
        return 1

    def get_latest_snapshot(
        self, db: Session, base_ccy: str, quote_ccy: str, target_date: str
    ) -> ExchangeRateIntradaySnapshotModel | None:
        """해당 거래일의 가장 최근 스냅샷(현재 상태)."""
        return (
            db.query(ExchangeRateIntradaySnapshotModel)
            .filter_by(base_ccy=base_ccy, quote_ccy=quote_ccy, target_date=target_date)
            .order_by(ExchangeRateIntradaySnapshotModel.observed_at.desc())
            .first()
        )

    def get_snapshot_asof(
        self,
        db: Session,
        base_ccy: str,
        quote_ccy: str,
        target_date: str,
        as_of: datetime,
    ) -> ExchangeRateIntradaySnapshotModel | None:
        """
        as_of 시점에 '그때 알던' 가장 최근 스냅샷(point-in-time).
        as_of는 tz-aware로 전달할 것(observed_at이 tz-aware이므로).
        """
        return (
            db.query(ExchangeRateIntradaySnapshotModel)
            .filter_by(base_ccy=base_ccy, quote_ccy=quote_ccy, target_date=target_date)
            .filter(ExchangeRateIntradaySnapshotModel.observed_at <= as_of)
            .order_by(ExchangeRateIntradaySnapshotModel.observed_at.desc())
            .first()
        )

    # ── 일별 종가 (upsert; base_rate 변동 시에만 갱신) ─────────
    def upsert_daily_quotes(self, db: Session, data: KBUsdKrwDailySeries) -> int:
        """Insert or update daily rows. 반환: 신규+변경 행 수."""
        now = _utcnow()
        affected = 0
        for quote in data.quotes:
            existing = (
                db.query(ExchangeRateDailyModel)
                .filter_by(
                    source=data.source,
                    base_ccy=data.base_ccy,
                    quote_ccy=data.quote_ccy,
                    quote_date=quote.quote_date,
                )
                .first()
            )
            if existing:
                if existing.base_rate != quote.base_rate:   # 값 변동 시에만
                    existing.base_rate = quote.base_rate
                    existing.ingested_at = now
                    affected += 1
            else:
                db.add(
                    ExchangeRateDailyModel(
                        source=data.source,
                        base_ccy=data.base_ccy,
                        quote_ccy=data.quote_ccy,
                        quote_date=quote.quote_date,
                        base_rate=quote.base_rate,
                        ingested_at=now,
                    )
                )
                affected += 1

        db.commit()
        logger.info(
            "Upserted %d daily quotes for %s/%s.",
            affected, data.base_ccy, data.quote_ccy,
        )
        return affected

    def get_daily_quotes(
        self,
        db: Session,
        base_ccy: str,
        quote_ccy: str,
        start_date: str,
        end_date: str,
    ) -> list[ExchangeRateDailyModel]:
        """[start_date, end_date] 구간 일별 행, 오래된 순."""
        return (
            db.query(ExchangeRateDailyModel)
            .filter(
                ExchangeRateDailyModel.base_ccy == base_ccy,
                ExchangeRateDailyModel.quote_ccy == quote_ccy,
                ExchangeRateDailyModel.quote_date >= start_date,
                ExchangeRateDailyModel.quote_date <= end_date,
            )
            .order_by(ExchangeRateDailyModel.quote_date.asc())
            .all()
        )
