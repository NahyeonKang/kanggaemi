"""
app/schemas/exchange_rate.py

Pydantic schemas for the exchange rate domain.

Two scraping modes are modeled separately:
  - Intraday summary (조회기준=1): one summary row per date
    → KBUsdKrwIntradaySummary
  - Daily series (조회기준=2): daily base-rate rows over a range
    → DailyQuote, KBUsdKrwDailySeries

Scraper-layer schemas are used internally by KBExchangeRateScraper and the
service layer. API-layer schemas are used by the FastAPI router.
"""
import re
from typing import Optional

from pydantic import BaseModel, Field, field_validator


# ---------------------------------------------------------------------------
# Scraper-layer schemas — intraday summary (조회기준=1)
# ---------------------------------------------------------------------------


class KBUsdKrwIntradaySummary(BaseModel):
    """
    Intraday USD/KRW summary returned by KBExchangeRateScraper.

    Parsed from the #summary1 / #summary3 tables (one row per date).
    """

    source: str = "kb_bank"
    currency: str = "USD/KRW"
    target_date: str                  # YYYY.MM.DD
    fetched_at: str                   # ISO datetime string
    first_rate: float                 # 최초 회차
    last_rate: float                  # 최종 회차
    daily_low: float                  # 일최저
    daily_high: float                 # 일최고
    daily_avg: float                  # 일평균


# ---------------------------------------------------------------------------
# Scraper-layer schemas — daily series (조회기준=2)
# ---------------------------------------------------------------------------


class DailyQuote(BaseModel):
    """Single daily base-rate row returned by the scraper."""

    quote_date: str                   # YYYY.MM.DD
    base_rate: float                  # 매매 기준율


class KBUsdKrwDailySeries(BaseModel):
    """Normalized daily USD/KRW series returned by KBExchangeRateScraper."""

    source: str = "kb_bank"
    currency: str = "USD/KRW"
    start_date: str                   # YYYY.MM.DD
    end_date: str                     # YYYY.MM.DD
    fetched_at: str                   # ISO datetime string
    quotes: list[DailyQuote] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# API request / response schemas — intraday summary
# ---------------------------------------------------------------------------


class ExchangeRateSummarySyncRequest(BaseModel):
    """Request body for syncing intraday summary by date."""

    search_date: Optional[str] = None  # YYYYMMDD

    @field_validator("search_date")
    @classmethod
    def validate_search_date(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        if not re.fullmatch(r"\d{8}", v):
            raise ValueError(
                "search_date must be in YYYYMMDD format (e.g. 20260612)."
            )
        return v


class ExchangeRateSummaryResponse(BaseModel):
    """Intraday summary for API responses."""

    source: str
    currency_code: str
    target_date: str
    first_rate: float
    last_rate: float
    daily_low: float
    daily_high: float
    daily_avg: float
    fetched_at: str

    model_config = {"from_attributes": True}


class ExchangeRateSummarySyncResponse(BaseModel):
    """Response body for the intraday summary sync endpoint."""

    source: str
    currency_code: str
    target_date: Optional[str]
    affected_count: int
    summary: ExchangeRateSummaryResponse


# ---------------------------------------------------------------------------
# API request / response schemas — daily series
# ---------------------------------------------------------------------------


class ExchangeRateRangeSyncRequest(BaseModel):
    """Request body for syncing a daily series over a date range."""

    start_date: str                    # YYYYMMDD
    end_date: Optional[str] = None     # YYYYMMDD, defaults to today

    @field_validator("start_date", "end_date")
    @classmethod
    def validate_dates(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        if not re.fullmatch(r"\d{8}", v):
            raise ValueError(
                "date must be in YYYYMMDD format (e.g. 20260612)."
            )
        return v


class ExchangeRateDailyResponse(BaseModel):
    """Single daily quote for API responses."""

    source: str
    currency_code: str
    quote_date: str
    base_rate: float
    fetched_at: str

    model_config = {"from_attributes": True}


class ExchangeRateRangeSyncResponse(BaseModel):
    """Response body for the daily series sync endpoint."""

    source: str
    currency_code: str
    start_date: str
    end_date: str
    affected_count: int
    quotes: list[ExchangeRateDailyResponse]