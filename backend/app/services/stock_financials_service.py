"""
app/services/stock_financials_service.py
"""
import logging
import re
from typing import Optional

from sqlalchemy.orm import Session

from app.models.stock_financials import StockFinancialsModel
from app.repositories.stock_financials_repository import StockFinancialsRepository
from app.scrapers.kis.kis_financials_scraper import KISFinancialsScraper, _PERIOD_TYPE

logger = logging.getLogger(__name__)

_ALLOWED_DIV_CLS = frozenset({"0", "1"})
_ALLOWED_PERIOD_TYPES = frozenset(_PERIOD_TYPE.values())
_YYMM_PATTERN = re.compile(r"^\d{6}$")


class StockFinancialsService:
    def __init__(self) -> None:
        self._scraper = KISFinancialsScraper()
        self._repo = StockFinancialsRepository()

    def sync_financials(
        self, db: Session, ticker: str, div_cls_code: str = "0"
    ) -> dict:
        self._validate_div_cls(div_cls_code)
        series = self._scraper.fetch_financials(ticker, div_cls_code)
        affected = self._repo.upsert_series(db, series)
        yymms = [o.stac_yymm for o in series.observations]
        return {
            "source": series.source,
            "ticker": ticker,
            "period_type": series.period_type,
            "affected_count": affected,
            "start_yymm": min(yymms) if yymms else None,
            "end_yymm": max(yymms) if yymms else None,
        }

    def get_financials(
        self,
        db: Session,
        ticker: str,
        period_type: str = "annual",
        start_yymm: Optional[str] = None,
        end_yymm: Optional[str] = None,
    ) -> list[StockFinancialsModel]:
        self._validate_period_type(period_type)
        self._validate_yymm(start_yymm)
        self._validate_yymm(end_yymm)
        return self._repo.get_series(db, ticker, period_type, start_yymm, end_yymm)

    # ── validations ──────────────────────────────────────────
    @staticmethod
    def _validate_div_cls(value: str) -> None:
        if value not in _ALLOWED_DIV_CLS:
            raise ValueError(f"div_cls_code must be one of {sorted(_ALLOWED_DIV_CLS)} (0=년,1=분기), got: {value!r}")

    @staticmethod
    def _validate_period_type(value: str) -> None:
        if value not in _ALLOWED_PERIOD_TYPES:
            raise ValueError(f"period_type must be one of {sorted(_ALLOWED_PERIOD_TYPES)}, got: {value!r}")

    @staticmethod
    def _validate_yymm(value: Optional[str]) -> None:
        if value is not None and not _YYMM_PATTERN.match(value):
            raise ValueError(f"yymm must be YYYYMM, got: {value!r}")