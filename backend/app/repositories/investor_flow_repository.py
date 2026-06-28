"""
app/repositories/investor_flow_repository.py

수급 데이터 접근 계층 (investor_flow_daily).
"""
import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.models.investor_flow import InvestorFlowDailyModel
from app.schemas.investor_flow import InvestorFlowSeries

logger = logging.getLogger(__name__)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class InvestorFlowRepository:
    """Repository for the investor_flow_daily table."""

    def upsert_flows(self, db: Session, series: InvestorFlowSeries) -> int:
        """series의 (date × investor_type) 관측을 upsert. 값 변동/신규만 카운트."""
        now = _utcnow()
        affected = 0
        for o in series.observations:
            existing = (
                db.query(InvestorFlowDailyModel)
                .filter_by(
                    source=series.source,
                    scope=series.scope,
                    market=series.market,
                    entity_code=series.entity_code,
                    investor_type=o.investor_type,
                    observation_date=o.observation_date,
                )
                .first()
            )
            if existing:
                if existing.net_qty != o.net_qty or existing.net_amount != o.net_amount:
                    existing.net_qty = o.net_qty
                    existing.net_amount = o.net_amount
                    existing.ingested_at = now
                    affected += 1
            else:
                db.add(
                    InvestorFlowDailyModel(
                        source=series.source,
                        scope=series.scope,
                        market=series.market,
                        entity_code=series.entity_code,
                        investor_type=o.investor_type,
                        observation_date=o.observation_date,
                        net_qty=o.net_qty,
                        net_amount=o.net_amount,
                        ingested_at=now,
                    )
                )
                affected += 1

        db.commit()
        logger.info(
            "Upserted %d flow rows for %s/%s/%s.",
            affected, series.scope, series.market, series.entity_code,
        )
        return affected

    def get_flows(
        self,
        db: Session,
        scope: str,
        entity_code: str,
        start_date: str,
        end_date: str,
        investor_type: Optional[str] = None,
        market: Optional[str] = None,
    ) -> list[InvestorFlowDailyModel]:
        """
        market은 시장 scope에서만 지정(KOSPI/KOSDAQ 구분). 종목은 티커가
        전역 고유라 market=None으로 조회.
        """
        query = db.query(InvestorFlowDailyModel).filter(
            InvestorFlowDailyModel.scope == scope,
            InvestorFlowDailyModel.entity_code == entity_code,
            InvestorFlowDailyModel.observation_date >= start_date,
            InvestorFlowDailyModel.observation_date <= end_date,
        )
        if market is not None:
            query = query.filter(InvestorFlowDailyModel.market == market)
        if investor_type is not None:
            query = query.filter(InvestorFlowDailyModel.investor_type == investor_type)
        return query.order_by(
            InvestorFlowDailyModel.observation_date.asc(),
            InvestorFlowDailyModel.investor_type.asc(),
        ).all()