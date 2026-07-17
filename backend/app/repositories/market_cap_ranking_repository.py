"""
app/repositories/market_cap_ranking_repository.py
"""
import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.models.market_cap_ranking import MarketCapRankingModel
from app.schemas.market_cap_ranking import MarketCapRanking

logger = logging.getLogger(__name__)

_VALUE_FIELDS = (
    "rank", "name", "close_price", "volume",
    "listed_shares", "market_cap", "market_weight",
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class MarketCapRankingRepository:
    def upsert_ranking(
        self, db: Session, ranking: MarketCapRanking, observation_date: str
    ) -> int:
        now = _utcnow()
        affected = 0
        for row in ranking.rows:
            existing = (
                db.query(MarketCapRankingModel)
                .filter_by(
                    source=ranking.source, market=ranking.market,
                    observation_date=observation_date, ticker=row.ticker,
                )
                .first()
            )
            if existing:
                if any(getattr(existing, f) != getattr(row, f) for f in _VALUE_FIELDS):
                    for f in _VALUE_FIELDS:
                        setattr(existing, f, getattr(row, f))
                    existing.ingested_at = now
                    affected += 1
            else:
                db.add(MarketCapRankingModel(
                    source=ranking.source, market=ranking.market,
                    observation_date=observation_date, ticker=row.ticker,
                    ingested_at=now,
                    **{f: getattr(row, f) for f in _VALUE_FIELDS},
                ))
                affected += 1
        db.commit()
        logger.info(
            "Upserted %d market-cap rows for %s (%s).",
            affected, ranking.market, observation_date,
        )
        return affected

    def get_ranking(
        self, db: Session, market: str, observation_date: str,
        top_n: Optional[int] = None,
    ) -> list[MarketCapRankingModel]:
        query = (
            db.query(MarketCapRankingModel)
            .filter_by(market=market, observation_date=observation_date)
            .order_by(MarketCapRankingModel.rank.asc())
        )
        if top_n is not None:
            query = query.limit(top_n)
        return query.all()

    def latest_date(self, db: Session, market: str) -> Optional[str]:
        row = (
            db.query(MarketCapRankingModel.observation_date)
            .filter_by(market=market)
            .order_by(MarketCapRankingModel.observation_date.desc())
            .first()
        )
        return row[0] if row else None