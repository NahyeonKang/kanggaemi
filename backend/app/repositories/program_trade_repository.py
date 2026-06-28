"""
app/repositories/program_trade_repository.py

프로그램매매 데이터 접근 계층 (program_trade_daily).
exchange_rate_daily 패턴: 값 변동 시에만 갱신, ingested_at은 기록 시점(UTC).
"""
import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.models.program_trade import ProgramTradeDailyModel
from app.schemas.program_trade import ProgramTradeSeries

logger = logging.getLogger(__name__)

_VALUE_FIELDS = ("sell_vol", "sell_amount", "buy_vol", "buy_amount", "net_qty", "net_amount")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ProgramTradeRepository:
    """Repository for the program_trade_daily table."""

    def upsert_series(self, db: Session, series: ProgramTradeSeries) -> int:
        now = _utcnow()
        affected = 0
        for o in series.observations:
            existing = (
                db.query(ProgramTradeDailyModel)
                .filter_by(
                    source=series.source,
                    scope=series.scope,
                    entity_code=series.entity_code,
                    trade_class=o.trade_class,
                    account_type=o.account_type,
                    observation_date=o.observation_date,
                )
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
                    ProgramTradeDailyModel(
                        source=series.source,
                        scope=series.scope,
                        entity_code=series.entity_code,
                        trade_class=o.trade_class,
                        account_type=o.account_type,
                        observation_date=o.observation_date,
                        ingested_at=now,
                        **{f: getattr(o, f) for f in _VALUE_FIELDS},
                    )
                )
                affected += 1

        db.commit()
        logger.info(
            "Upserted %d program rows for %s/%s.",
            affected, series.scope, series.entity_code,
        )
        return affected

    def get_series(
        self,
        db: Session,
        scope: str,
        entity_code: str,
        start_date: str,
        end_date: str,
        trade_class: Optional[str] = None,
        account_type: Optional[str] = None,
    ) -> list[ProgramTradeDailyModel]:
        query = db.query(ProgramTradeDailyModel).filter(
            ProgramTradeDailyModel.scope == scope,
            ProgramTradeDailyModel.entity_code == entity_code,
            ProgramTradeDailyModel.observation_date >= start_date,
            ProgramTradeDailyModel.observation_date <= end_date,
        )
        if trade_class is not None:
            query = query.filter(ProgramTradeDailyModel.trade_class == trade_class)
        if account_type is not None:
            query = query.filter(ProgramTradeDailyModel.account_type == account_type)
        return query.order_by(
            ProgramTradeDailyModel.observation_date.asc(),
            ProgramTradeDailyModel.trade_class.asc(),
            ProgramTradeDailyModel.account_type.asc(),
        ).all()