"""
app/repositories/stock_financials_repository.py
"""
import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.models.stock_financials import StockFinancialsModel
from app.schemas.stock_financials import FinancialsSeries

logger = logging.getLogger(__name__)

_VALUE_FIELDS = (
    "revenue_growth", "op_income_growth", "net_income_growth", "roe", "eps",
    "net_profit_margin", "ev_ebitda", "revenue", "op_income",
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class StockFinancialsRepository:
    def upsert_series(self, db: Session, series: FinancialsSeries) -> int:
        now = _utcnow()
        affected = 0
        for o in series.observations:
            existing = (
                db.query(StockFinancialsModel)
                .filter_by(
                    source=series.source, ticker=series.ticker,
                    period_type=series.period_type, stac_yymm=o.stac_yymm,
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
                    StockFinancialsModel(
                        source=series.source, ticker=series.ticker,
                        period_type=series.period_type, stac_yymm=o.stac_yymm,
                        ingested_at=now,
                        **{f: getattr(o, f) for f in _VALUE_FIELDS},
                    )
                )
                affected += 1
        db.commit()
        logger.info(
            "Upserted %d financials rows for %s (%s).",
            affected, series.ticker, series.period_type,
        )
        return affected

    def get_series(
        self,
        db: Session,
        ticker: str,
        period_type: str,
        start_yymm: Optional[str] = None,
        end_yymm: Optional[str] = None,
    ) -> list[StockFinancialsModel]:
        query = db.query(StockFinancialsModel).filter(
            StockFinancialsModel.ticker == ticker,
            StockFinancialsModel.period_type == period_type,
        )
        if start_yymm:
            query = query.filter(StockFinancialsModel.stac_yymm >= start_yymm)
        if end_yymm:
            query = query.filter(StockFinancialsModel.stac_yymm <= end_yymm)
        return query.order_by(StockFinancialsModel.stac_yymm.desc()).all()

    def get_series_asof(
        self, db: Session, ticker: str, period_type: str,
        start_yymm: str, end_yymm: str, ingested_asof: datetime,
    ) -> list[StockFinancialsModel]:
        """Exclude statements that were not yet present at the analysis cutoff."""
        return (
            db.query(StockFinancialsModel)
            .filter(
                StockFinancialsModel.ticker == ticker,
                StockFinancialsModel.period_type == period_type,
                StockFinancialsModel.stac_yymm >= start_yymm,
                StockFinancialsModel.stac_yymm <= end_yymm,
                StockFinancialsModel.ingested_at <= ingested_asof,
            )
            .order_by(StockFinancialsModel.stac_yymm.asc())
            .all()
        )
