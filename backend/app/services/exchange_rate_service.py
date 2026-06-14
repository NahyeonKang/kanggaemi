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

from app.models.exchange_rate import (
    ExchangeRateSummaryModel,
    ExchangeRateDailyModel,
)
from app.repositories.exchange_rate_repository import ExchangeRateRepository
from app.scrapers.exchange_rate.kb_exchange_rate_scraper import KBExchangeRateScraper

logger = logging.getLogger(__name__)


class ExchangeRateService:
    def __init__(self) -> None:
        self._scraper = KBExchangeRateScraper()
        self._repo = ExchangeRateRepository()
        self._kst = ZoneInfo("Asia/Seoul")
        self._kr_holidays = holidays.KR()

    # ── 장중 요약 ────────────────────────────────────────────
    def sync_usdkrw_summary(
        self, db: Session, search_date: Optional[str] = None
    ) -> dict:
        """search_date: YYYYMMDD 또는 YYYY.MM.DD. 생략 시 자동 결정."""
        if search_date is not None:
            search_date = self._normalize_to_yyyymmdd(search_date)

        resolved = search_date or self._resolve_search_date()
        logger.info("Syncing USD/KRW summary for %s.", resolved)

        data = self._scraper.fetch_usdkrw_summary(search_date=resolved)
        affected = self._repo.upsert_summary(db, data)
        currency_code = data.currency.split("/")[0]

        return {
            "source": data.source,
            "currency_code": currency_code,
            "target_date": data.target_date,
            "affected_count": affected,
            "summary": {
                "source": data.source,
                "currency_code": currency_code,
                "target_date": data.target_date,
                "first_rate": data.first_rate,
                "last_rate": data.last_rate,
                "daily_low": data.daily_low,
                "daily_high": data.daily_high,
                "daily_avg": data.daily_avg,
                "fetched_at": data.fetched_at,
            },
        }

    def get_summary(
        self, db: Session, currency_code: str, target_date: str
    ) -> Optional[ExchangeRateSummaryModel]:
        normalized = self._normalize_to_yyyy_mm_dd(target_date)
        return self._repo.get_summary_by_date(
            db, currency_code=currency_code, target_date=normalized
        )

    # ── 일별 종가 ────────────────────────────────────────────
    def sync_usdkrw_daily(
        self, db: Session, start_date: str, end_date: Optional[str] = None
    ) -> dict:
        """start_date / end_date: YYYYMMDD 또는 YYYY.MM.DD."""
        start = self._normalize_to_yyyymmdd(start_date)
        end = self._normalize_to_yyyymmdd(end_date) if end_date else None
        logger.info("Syncing USD/KRW daily series for %s ~ %s.", start, end or "today")

        data = self._scraper.fetch_usdkrw_range(start_date=start, end_date=end)
        affected = self._repo.upsert_daily_quotes(db, data)
        currency_code = data.currency.split("/")[0]

        return {
            "source": data.source,
            "currency_code": currency_code,
            "start_date": data.start_date,
            "end_date": data.end_date,
            "affected_count": affected,
            "quotes": [
                {
                    "source": data.source,
                    "currency_code": currency_code,
                    "quote_date": q.quote_date,
                    "base_rate": q.base_rate,
                    "fetched_at": data.fetched_at,
                }
                for q in data.quotes
            ],
        }

    def get_daily(
        self,
        db: Session,
        currency_code: str,
        start_date: str,
        end_date: str,
    ) -> list[ExchangeRateDailyModel]:
        start = self._normalize_to_yyyy_mm_dd(start_date)
        end = self._normalize_to_yyyy_mm_dd(end_date)
        return self._repo.get_daily_quotes(
            db, currency_code=currency_code, start_date=start, end_date=end
        )

    # ── Private helpers ──────────────────────────────────────
    @staticmethod
    def _normalize_to_yyyymmdd(raw: str) -> str:
        if re.fullmatch(r"\d{8}", raw):
            return raw
        if re.fullmatch(r"\d{4}\.\d{2}\.\d{2}", raw):
            return raw.replace(".", "")
        raise ValueError(f"date must be YYYYMMDD or YYYY.MM.DD, got: {raw!r}")

    @staticmethod
    def _normalize_to_yyyy_mm_dd(raw: str) -> str:
        if re.fullmatch(r"\d{8}", raw):
            return f"{raw[:4]}.{raw[4:6]}.{raw[6:]}"
        if re.fullmatch(r"\d{4}\.\d{2}\.\d{2}", raw):
            return raw
        raise ValueError(f"date must be YYYYMMDD or YYYY.MM.DD, got: {raw!r}")

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