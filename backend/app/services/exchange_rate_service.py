"""
app/services/exchange_rate_service.py

Business logic for exchange rate data: scraping, persistence, and retrieval.
"""

import logging
from datetime import date, datetime, timedelta
from typing import Optional
from zoneinfo import ZoneInfo

import holidays
from sqlalchemy.orm import Session

from app.models.exchange_rate import ExchangeRateQuoteModel
from app.repositories.exchange_rate_repository import ExchangeRateRepository
from app.scrapers.exchange_rate.kb_exchange_rate_scraper import KBExchangeRateScraper

logger = logging.getLogger(__name__)


class ExchangeRateService:
    """
    Orchestrates scraping, persistence, and retrieval of exchange rate quotes.

    Rules for automatic search_date resolution:
    - If today is not a Korean business day, use the most recent previous business day.
    - If today is a business day but current time is before 08:30 KST, use the most recent previous business day.
    - Otherwise, use today.
    """

    def __init__(self) -> None:
        self._scraper = KBExchangeRateScraper()
        self._repo = ExchangeRateRepository()
        self._kst = ZoneInfo("Asia/Seoul")
        self._kr_holidays = holidays.KR()

    def sync_usdkrw_quotes(
        self,
        db: Session,
        search_date: Optional[str] = None,
    ) -> dict:
        """
        Fetch intraday USD/KRW quotes from KB Bank and persist them.

        Args:
            db: SQLAlchemy session.
            search_date: Date string in YYYYMMDD format. If omitted, it is resolved automatically.

        Returns:
            Dict with source, currency_code, target_date, affected_count, quotes.
        """
        resolved_search_date = search_date or self._resolve_search_date()
        logger.info("Syncing USD/KRW quotes for %s.", resolved_search_date)

        kb_data = self._scraper.fetch_usdkrw(search_date=resolved_search_date)
        affected = self._repo.upsert_quotes(db, kb_data)

        currency_code = kb_data.currency.split("/")[0]
        fetched_at = kb_data.fetched_at or ""

        return {
            "source": kb_data.source,
            "currency_code": currency_code,
            "target_date": kb_data.target_date,
            "affected_count": affected,
            "resolved_search_date": resolved_search_date,
            "quotes": [
                {
                    "source": kb_data.source,
                    "currency_code": currency_code,
                    "target_date": kb_data.target_date or "",
                    "quote_time": q.quote_time,
                    "base_rate": q.base_rate,
                    "fetched_at": fetched_at,
                }
                for q in kb_data.quotes
            ],
        }

    def get_quotes(
        self,
        db: Session,
        currency_code: str,
        target_date: str,
    ) -> list[ExchangeRateQuoteModel]:
        """
        Return stored quotes for a given currency and date.

        Args:
            db: SQLAlchemy session.
            currency_code: e.g. "USD".
            target_date: YYYY.MM.DD format.
        """
        return self._repo.get_latest_quotes_by_date(
            db, currency_code=currency_code, target_date=target_date
        )

    def _resolve_search_date(self) -> str:
        """
        Resolve search_date in YYYYMMDD format using Korean business-day rules.
        """
        now = datetime.now(self._kst)
        today = now.date()

        if not self._is_business_day(today):
            target = self._get_previous_business_day(today)
        elif (now.hour, now.minute) < (8, 30):
            target = self._get_previous_business_day(today)
        else:
            target = today

        return target.strftime("%Y%m%d")

    def _get_previous_business_day(self, current_date: date) -> date:
        candidate = current_date - timedelta(days=1)
        while not self._is_business_day(candidate):
            candidate -= timedelta(days=1)
        return candidate

    def _is_business_day(self, target_date: date) -> bool:
        # Saturday=5, Sunday=6
        if target_date.weekday() >= 5:
            return False

        if target_date in self._kr_holidays:
            return False

        return True