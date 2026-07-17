from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.market_cap_ranking import MarketCapRankingModel
from app.models.universe_membership import UniverseMembershipModel


class UniverseMembershipRepository:
    def upsert_market_snapshot(
        self,
        db: Session,
        univ_date: str,
        market: str,
        rows: list[MarketCapRankingModel],
    ) -> int:
        now = datetime.now(timezone.utc)
        affected = 0
        for row in rows:
            existing = (
                db.query(UniverseMembershipModel)
                .filter_by(univ_date=univ_date, market=market, ticker=row.ticker)
                .first()
            )
            if existing is None:
                db.add(
                    UniverseMembershipModel(
                        univ_date=univ_date,
                        market=market,
                        ticker=row.ticker,
                        rank=row.rank,
                        market_cap=row.market_cap,
                        ingested_at=now,
                    )
                )
                affected += 1
            elif existing.rank != row.rank or existing.market_cap != row.market_cap:
                existing.rank = row.rank
                existing.market_cap = row.market_cap
                existing.ingested_at = now
                affected += 1
        db.commit()
        return affected

    def latest_date(self, db: Session) -> str | None:
        return db.query(func.max(UniverseMembershipModel.univ_date)).scalar()

    def latest_complete_date(self, db: Session, expected_counts: dict[str, int]) -> str | None:
        dates = [
            value
            for (value,) in (
                db.query(UniverseMembershipModel.univ_date)
                .distinct()
                .order_by(UniverseMembershipModel.univ_date.desc())
                .all()
            )
        ]
        for univ_date in dates:
            counts = dict(
                db.query(UniverseMembershipModel.market, func.count(UniverseMembershipModel.id))
                .filter_by(univ_date=univ_date)
                .group_by(UniverseMembershipModel.market)
                .all()
            )
            if all(counts.get(market, 0) >= count for market, count in expected_counts.items()):
                return univ_date
        return None

    def get_latest(
        self, db: Session, expected_counts: dict[str, int] | None = None
    ) -> list[UniverseMembershipModel]:
        latest = (
            self.latest_complete_date(db, expected_counts)
            if expected_counts is not None
            else self.latest_date(db)
        )
        if latest is None:
            return []
        return (
            db.query(UniverseMembershipModel)
            .filter_by(univ_date=latest)
            .order_by(UniverseMembershipModel.market.asc(), UniverseMembershipModel.rank.asc())
            .all()
        )

    def get_latest_tickers(
        self, db: Session, expected_counts: dict[str, int] | None = None
    ) -> list[str]:
        return [row.ticker for row in self.get_latest(db, expected_counts)]
