"""
app/services/exchange_rate_service.py

환율 비즈니스 로직: 스크래핑, 적재, 조회.
"""
import logging
import re
from datetime import date, datetime, timedelta
from typing import Optional
from zoneinfo import ZoneInfo

import holidays
from sqlalchemy.orm import Session

from app.models.exchange_rate import (
    ExchangeRateIntradaySnapshotModel,
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

    # ── 장중 스냅샷 ──────────────────────────────────────────
    def sync_usdkrw_summary(
        self, db: Session, search_date: Optional[str] = None
    ) -> dict:
        """search_date: YYYYMMDD 또는 YYYY.MM.DD. 생략 시 자동 결정."""
        if search_date is not None:
            search_date = self._normalize_to_yyyymmdd(search_date)

        resolved = search_date or self._resolve_search_date()
        logger.info("Syncing USD/KRW summary for %s.", resolved)

        data = self._scraper.fetch_usdkrw_summary(search_date=resolved)
        affected = self._repo.insert_snapshot(db, data)

        return {
            "source": data.source,
            "base_ccy": data.base_ccy,
            "quote_ccy": data.quote_ccy,
            "target_date": data.target_date,
            "observed_at": data.observed_at.isoformat(),
            "affected_count": affected,
            "snapshot": {
                "first_rate": data.first_rate,
                "last_rate": data.last_rate,
                "daily_low": data.daily_low,
                "daily_high": data.daily_high,
                "daily_avg": data.daily_avg,
            },
        }

    def get_latest_summary(
        self,
        db: Session,
        target_date: str,
        base_ccy: str = "USD",
        quote_ccy: str = "KRW",
    ) -> Optional[ExchangeRateIntradaySnapshotModel]:
        """해당 거래일의 현재(가장 최근) 스냅샷."""
        normalized = self._normalize_to_yyyy_mm_dd(target_date)
        return self._repo.get_latest_snapshot(db, base_ccy, quote_ccy, normalized)

    def get_summary_asof(
        self,
        db: Session,
        target_date: str,
        as_of: datetime,
        base_ccy: str = "USD",
        quote_ccy: str = "KRW",
    ) -> Optional[ExchangeRateIntradaySnapshotModel]:
        """as_of 시점 기준 point-in-time 스냅샷. as_of는 tz-aware로 전달."""
        normalized = self._normalize_to_yyyy_mm_dd(target_date)
        return self._repo.get_snapshot_asof(
            db, base_ccy, quote_ccy, normalized, as_of
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

        return {
            "source": data.source,
            "base_ccy": data.base_ccy,
            "quote_ccy": data.quote_ccy,
            "start_date": data.start_date,
            "end_date": data.end_date,
            "observed_at": data.observed_at.isoformat(),
            "affected_count": affected,
            "quotes": [
                {"quote_date": q.quote_date, "base_rate": q.base_rate}
                for q in data.quotes
            ],
        }

    def get_daily(
        self,
        db: Session,
        start_date: str,
        end_date: str,
        base_ccy: str = "USD",
        quote_ccy: str = "KRW",
    ) -> list[ExchangeRateDailyModel]:
        start = self._normalize_to_yyyy_mm_dd(start_date)
        end = self._normalize_to_yyyy_mm_dd(end_date)
        return self._repo.get_daily_quotes(db, base_ccy, quote_ccy, start, end)

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