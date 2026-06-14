"""
app/scrapers/exchange_rate/base.py

Abstract base interface for exchange rate scrapers.
"""
from abc import ABC, abstractmethod
from typing import Optional

from app.schemas.exchange_rate import (
    KBUsdKrwIntradaySummary,
    KBUsdKrwDailySeries,
)


class BaseExchangeRateScraper(ABC):
    """Base interface for exchange rate scrapers."""

    @abstractmethod
    def fetch_usdkrw_summary(
        self, search_date: Optional[str] = None
    ) -> KBUsdKrwIntradaySummary:
        """Fetch the intraday USD/KRW summary for a given date."""
        raise NotImplementedError

    @abstractmethod
    def fetch_usdkrw_range(
        self, start_date: str, end_date: Optional[str] = None
    ) -> KBUsdKrwDailySeries:
        """Fetch the daily USD/KRW base-rate series over a date range."""
        raise NotImplementedError