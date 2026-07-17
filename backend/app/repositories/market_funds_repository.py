"""
app/repositories/market_funds_repository.py

증시자금 데이터 접근 계층. 값 변동 시에만 갱신(ingested_at=UTC).
"""
import logging
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.market_funds import MarketFundsDailyModel
from app.schemas.market_funds import MarketFundsSeries

logger = logging.getLogger(__name__)

_VALUE_FIELDS = (
    "customer_deposit", "customer_deposit_change", "amount_turnover",
    "receivable", "credit_loan_balance", "futures_deposit",
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class MarketFundsRepository:
    def upsert_series(self, db: Session, series: MarketFundsSeries) -> int:
        now = _utcnow()
        affected = 0
        for o in series.observations:
            existing = (
                db.query(MarketFundsDailyModel)
                .filter_by(source=series.source, observation_date=o.observation_date)
                .first()
            )
            if existing:
                if any(getattr(existing, f) != getattr(o, f) for f in _VALUE_FIELDS):
                    for f in _VALUE_FIELDS:
                        setattr(existing, f, getattr(o, f))
                    existing.ingested_at = now
                    affected += 1
            else:
                db.add(
                    MarketFundsDailyModel(
                        source=series.source,
                        observation_date=o.observation_date,
                        ingested_at=now,
                        **{f: getattr(o, f) for f in _VALUE_FIELDS},
                    )
                )
                affected += 1
        db.commit()
        logger.info("Upserted %d market-funds rows.", affected)
        return affected

    def get_series(
        self, db: Session, start_date: str, end_date: str
    ) -> list[MarketFundsDailyModel]:
        return (
            db.query(MarketFundsDailyModel)
            .filter(
                MarketFundsDailyModel.observation_date >= start_date,
                MarketFundsDailyModel.observation_date <= end_date,
            )
            .order_by(MarketFundsDailyModel.observation_date.asc())
            .all()
        )