"""
app/services/exchange_rate_service.py

Business logic for exchange rate data: scraping, persistence, and retrieval.
"""

import logging
import re
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
        search_date: YYYYMMDD 또는 YYYY.MM.DD 모두 허용. 생략 시 자동 결정.
        """
        if search_date is not None:
            # 스크래퍼가 YYYYMMDD를 요구하므로 해당 포맷으로 정규화
            search_date = self._normalize_to_yyyymmdd(search_date)

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
        target_date: YYYYMMDD 또는 YYYY.MM.DD 모두 허용.
        DB 조회는 YYYY.MM.DD 포맷 사용.
        """
        normalized = self._normalize_to_yyyy_mm_dd(target_date)
        return self._repo.get_latest_quotes_by_date(
            db, currency_code=currency_code, target_date=normalized
        )

    # ------------------------------------------------------------------ #
    # Private helpers                                                      #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _normalize_to_yyyymmdd(raw: str) -> str:
        """YYYYMMDD 또는 YYYY.MM.DD → YYYYMMDD"""
        if re.fullmatch(r"\d{8}", raw):
            return raw
        if re.fullmatch(r"\d{4}\.\d{2}\.\d{2}", raw):
            return raw.replace(".", "")
        raise ValueError(
            f"target_date must be YYYYMMDD or YYYY.MM.DD, got: {raw!r}"
        )

    @staticmethod
    def _normalize_to_yyyy_mm_dd(raw: str) -> str:
        """YYYYMMDD 또는 YYYY.MM.DD → YYYY.MM.DD"""
        if re.fullmatch(r"\d{8}", raw):
            return f"{raw[:4]}.{raw[4:6]}.{raw[6:]}"
        if re.fullmatch(r"\d{4}\.\d{2}\.\d{2}", raw):
            return raw
        raise ValueError(
            f"target_date must be YYYYMMDD or YYYY.MM.DD, got: {raw!r}"
        )

    def _resolve_search_date(self) -> str:
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
        if target_date.weekday() >= 5:
            return False
        if target_date in self._kr_holidays:
            return False
        return True