"""
app/repositories/instrument_price_repository.py

시세 데이터 접근 계층 (통합).
  - instrument_ohlcv          : 값 변동 시 갱신.
  - stock_valuation_snapshot  : append-only, as-of.
  - derivative_snapshot       : append-only, as-of.
"""
import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.models.instrument_price import (
    InstrumentOhlcvModel, StockValuationSnapshotModel, DerivativeSnapshotModel,
)
from app.schemas.instrument_price import (
    OhlcvObservation, StockValuationSnapshot, DerivativeSnapshot,
)

logger = logging.getLogger(__name__)

_OHLCV_FIELDS = ("open", "high", "low", "close", "volume", "amount")
_VAL_FIELDS = (
    "name", "current_price", "upper_limit", "lower_limit", "vol_turnover",
    "listed_shares", "market_cap", "per", "pbr",
)
_DERIV_FIELDS = (
    "name", "current_price", "upper_limit", "lower_limit", "basis", "kospi200",
    "open_interest", "oi_change", "theoretical_price", "disparity", "tick_strength",
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class InstrumentPriceRepository:
    # ── OHLCV ────────────────────────────────────────────────
    def upsert_ohlcv(
        self,
        db: Session,
        source: str,
        asset_class: str,
        entity_code: str,
        resolution: str,
        rows: list[OhlcvObservation],
        currency: Optional[str] = None,
    ) -> int:
        now = _utcnow()
        affected = 0
        for o in rows:
            existing = (
                db.query(InstrumentOhlcvModel)
                .filter_by(
                    source=source, asset_class=asset_class, entity_code=entity_code,
                    resolution=resolution, observation_date=o.observation_date,
                )
                .first()
            )
            if existing:
                if any(getattr(existing, f) != getattr(o, f) for f in _OHLCV_FIELDS):
                    for f in _OHLCV_FIELDS:
                        setattr(existing, f, getattr(o, f))
                    existing.ingested_at = now
                    affected += 1
                # currency는 심볼별로 안정적 → 값이 다를 때만 보정(변경 카운트엔 미포함)
                if currency is not None and existing.currency != currency:
                    existing.currency = currency
            else:
                db.add(
                    InstrumentOhlcvModel(
                        source=source, asset_class=asset_class, entity_code=entity_code,
                        resolution=resolution, observation_date=o.observation_date,
                        currency=currency, ingested_at=now,
                        **{f: getattr(o, f) for f in _OHLCV_FIELDS},
                    )
                )
                affected += 1
        db.commit()
        logger.info(
            "Upserted %d OHLCV rows for %s/%s (%s).",
            affected, asset_class, entity_code, resolution,
        )
        return affected

    def get_ohlcv(
        self, db: Session, asset_class: str, entity_code: str,
        resolution: str, start_date: str, end_date: str,
    ) -> list[InstrumentOhlcvModel]:
        return (
            db.query(InstrumentOhlcvModel)
            .filter(
                InstrumentOhlcvModel.asset_class == asset_class,
                InstrumentOhlcvModel.entity_code == entity_code,
                InstrumentOhlcvModel.resolution == resolution,
                InstrumentOhlcvModel.observation_date >= start_date,
                InstrumentOhlcvModel.observation_date <= end_date,
            )
            .order_by(InstrumentOhlcvModel.observation_date.asc())
            .all()
        )

    # ── 주식 valuation 스냅샷 ────────────────────────────────
    def insert_valuation_snapshot(
        self, db: Session, source: str, ticker: str,
        valuation: StockValuationSnapshot, observed_at: datetime,
    ) -> int:
        if db.query(StockValuationSnapshotModel.id).filter_by(
            source=source, ticker=ticker, observed_at=observed_at
        ).first():
            return 0
        db.add(StockValuationSnapshotModel(
            source=source, ticker=ticker, observed_at=observed_at, ingested_at=_utcnow(),
            **{f: getattr(valuation, f) for f in _VAL_FIELDS},
        ))
        db.commit()
        return 1

    def get_latest_valuation(self, db: Session, ticker: str):
        return (
            db.query(StockValuationSnapshotModel)
            .filter_by(ticker=ticker)
            .order_by(StockValuationSnapshotModel.observed_at.desc())
            .first()
        )

    def get_valuation_asof(self, db: Session, ticker: str, as_of: datetime):
        return (
            db.query(StockValuationSnapshotModel)
            .filter_by(ticker=ticker)
            .filter(StockValuationSnapshotModel.observed_at <= as_of)
            .order_by(StockValuationSnapshotModel.observed_at.desc())
            .first()
        )

    # ── 파생 스냅샷 ──────────────────────────────────────────
    def insert_derivative_snapshot(
        self, db: Session, source: str, entity_code: str,
        derivative: DerivativeSnapshot, observed_at: datetime,
    ) -> int:
        if db.query(DerivativeSnapshotModel.id).filter_by(
            source=source, entity_code=entity_code, observed_at=observed_at
        ).first():
            return 0
        db.add(DerivativeSnapshotModel(
            source=source, entity_code=entity_code, observed_at=observed_at,
            ingested_at=_utcnow(),
            **{f: getattr(derivative, f) for f in _DERIV_FIELDS},
        ))
        db.commit()
        return 1

    def get_latest_derivative(self, db: Session, entity_code: str):
        return (
            db.query(DerivativeSnapshotModel)
            .filter_by(entity_code=entity_code)
            .order_by(DerivativeSnapshotModel.observed_at.desc())
            .first()
        )

    def get_derivative_asof(self, db: Session, entity_code: str, as_of: datetime):
        return (
            db.query(DerivativeSnapshotModel)
            .filter_by(entity_code=entity_code)
            .filter(DerivativeSnapshotModel.observed_at <= as_of)
            .order_by(DerivativeSnapshotModel.observed_at.desc())
            .first()
        )