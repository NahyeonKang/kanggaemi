"""
app/scrapers/exchange_rate/base.py

Abstract base interface for exchange rate scrapers.
"""
from abc import ABC, abstractmethod

from app.schemas.exchange_rate import KBUsdKrwExchangeRate


class BaseExchangeRateScraper(ABC):
    """Base interface for exchange rate scrapers."""

    @abstractmethod
    def fetch_usdkrw(self) -> KBUsdKrwExchangeRate:
        """Fetch the current USD/KRW exchange rate end-to-end."""
        raise NotImplementedError

