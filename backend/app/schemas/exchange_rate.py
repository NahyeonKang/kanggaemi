"""
app/schemas/exchange_rate.py

Pydantic schemas for the exchange rate domain.

Scraper-layer schemas (IntradayQuote, KBUsdKrwExchangeRate) are used
internally by KBExchangeRateScraper and the service layer.

API-layer schemas (ExchangeRateSyncRequest, ExchangeRateQuoteResponse,
ExchangeRateSyncResponse) are used by the FastAPI router.
"""
import re
from typing import Optional

from pydantic import BaseModel, Field, field_validator


# ---------------------------------------------------------------------------
# Scraper-layer schemas
# ---------------------------------------------------------------------------


class IntradayQuote(BaseModel):
    """Single intraday exchange rate quote returned by the scraper."""

    quote_time: str   # HH:MM:SS
    base_rate: float  # 매매 기준율


class KBUsdKrwExchangeRate(BaseModel):
    """Normalized USD/KRW data returned by KBExchangeRateScraper."""

    source: str = "kb_bank"
    currency: str = "USD/KRW"
    target_date: Optional[str] = None     # YYYY.MM.DD
    daily_low: Optional[float] = None
    daily_high: Optional[float] = None
    daily_average: Optional[float] = None
    fetched_at: Optional[str] = None      # ISO datetime string
    quotes: list[IntradayQuote] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# API request / response schemas
# ---------------------------------------------------------------------------


class ExchangeRateSyncRequest(BaseModel):
    """Request body for POST /exchange-rate/usdkrw/sync."""

    search_date: Optional[str] = None  # YYYYMMDD

    @field_validator("search_date")
    @classmethod
    def validate_search_date(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v

        if not re.fullmatch(r"\d{8}", v):
            raise ValueError(
                "search_date must be in YYYYMMDD format (e.g. 20260305)."
            )

        return v


class ExchangeRateQuoteResponse(BaseModel):
    """Single exchange rate quote for API responses."""

    source: str
    currency_code: str
    target_date: str
    quote_time: str
    base_rate: float
    fetched_at: str

    model_config = {"from_attributes": True}


class ExchangeRateSyncResponse(BaseModel):
    """Response body for POST /exchange-rate/usdkrw/sync."""

    source: str
    currency_code: str
    target_date: Optional[str]
    affected_count: int
    quotes: list[ExchangeRateQuoteResponse]
