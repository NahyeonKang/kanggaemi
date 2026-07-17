"""
app/services/market_funds_service.py

증시자금 비즈니스 로직. 한 번의 sync로 기준일 이전 시계열 upsert.
"""
import logging
import re
from typing import Optional

from sqlalchemy.orm import Session

from app.models.market_funds import MarketFundsDailyModel
from app.repositories.market_funds_repository import MarketFundsRepository
from app.scrapers.kis.kis_market_funds_scraper import KISMarketFundsScraper

logger = logging.getLogger(__name__)

_DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_YYYYMMDD_PATTERN = re.compile(r"^\d{8}$")


class MarketFundsService:
    def __init__(self) -> None:
        self._scraper = KISMarketFundsScraper()
        self._repo = MarketFundsRepository()

    def sync_market_funds(self, db: Session, date: Optional[str] = None) -> dict:
        self._validate_yyyymmdd(date)
        series = self._scraper.fetch_market_funds(date or "")
        affected = self._repo.upsert_series(db, series)
        dates = [o.observation_date for o in series.observations]
        return {
            "source": series.source,
            "affected_count": affected,
            "start_date": min(dates) if dates else None,
            "end_date": max(dates) if dates else None,
        }

    def get_market_funds(
        self, db: Session, start_date: str, end_date: str
    ) -> list[MarketFundsDailyModel]:
        self._validate_date(start_date, "start_date")
        self._validate_date(end_date, "end_date")
        return self._repo.get_series(db, start_date, end_date)

    # ── validations ──────────────────────────────────────────
    @staticmethod
    def _validate_date(value: str, field_name: str) -> None:
        if not _DATE_PATTERN.match(value):
            raise ValueError(f"{field_name} must be YYYY-MM-DD, got: {value!r}")

    @staticmethod
    def _validate_yyyymmdd(value: Optional[str]) -> None:
        if value is not None and not _YYYYMMDD_PATTERN.match(value):
            raise ValueError(f"date must be YYYYMMDD, got: {value!r}")