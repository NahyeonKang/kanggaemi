"""
app/schemas/exchange_rate.py

Pydantic schemas for the exchange rate domain.

Two scraping modes are modeled separately:
  - Intraday summary (조회기준=1): append-only snapshot per (date, observed_at)
    → KBUsdKrwIntradaySummary
  - Daily series (조회기준=2): daily base-rate rows over a range
    → DailyQuote, KBUsdKrwDailySeries

Scraper-layer schemas are used internally by KBExchangeRateScraper and the
service layer. API-layer schemas are used by the FastAPI router.
"""
import re
from typing import Optional
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, field_validator


# ---------------------------------------------------------------------------
# Scraper-layer schemas — intraday summary (조회기준=1)
# ---------------------------------------------------------------------------


class KBUsdKrwIntradaySummary(BaseModel):
    """장중 요약 스냅샷 1건."""

    model_config = ConfigDict(from_attributes=True)

    source: str = "KB"
    base_ccy: str = "USD"
    quote_ccy: str = "KRW"
    target_date: str                 # "YYYY.MM.DD" (event date)
    observed_at: datetime            # 스냅샷이 반영하는 시점 (tz-aware)
    first_rate: Decimal
    last_rate: Decimal
    daily_low: Decimal
    daily_high: Decimal
    daily_avg: Decimal


# ---------------------------------------------------------------------------
# Scraper-layer schemas — daily series (조회기준=2)
# ---------------------------------------------------------------------------


class DailyQuote(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    quote_date: str                  # "YYYY.MM.DD"
    base_rate: Decimal


class KBUsdKrwDailySeries(BaseModel):
    """일별 종가 시리즈."""

    model_config = ConfigDict(from_attributes=True)

    source: str = "KB"
    base_ccy: str = "USD"
    quote_ccy: str = "KRW"
    start_date: str
    end_date: str
    observed_at: datetime            # 시리즈 fetch 시각 (tz-aware)
    quotes: list[DailyQuote]


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
    """저장된 장중 스냅샷 1건 (GET 응답). ORM 행에서 직접 매핑."""

    model_config = ConfigDict(from_attributes=True)

    source: str
    base_ccy: str
    quote_ccy: str
    target_date: str
    observed_at: datetime
    first_rate: Decimal
    last_rate: Decimal
    daily_low: Decimal
    daily_high: Decimal
    daily_avg: Decimal
    ingested_at: datetime


class ExchangeRateSnapshotValues(BaseModel):
    """sync 응답에서 에코하는 스냅샷 값."""

    first_rate: Decimal
    last_rate: Decimal
    daily_low: Decimal
    daily_high: Decimal
    daily_avg: Decimal


class ExchangeRateSummarySyncResponse(BaseModel):
    """Response body for the intraday summary sync endpoint."""

    source: str
    base_ccy: str
    quote_ccy: str
    target_date: Optional[str]
    observed_at: datetime
    affected_count: int
    snapshot: ExchangeRateSnapshotValues


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
    """저장된 일별 종가 1건 (GET 응답). ORM 행에서 직접 매핑."""

    model_config = ConfigDict(from_attributes=True)

    source: str
    base_ccy: str
    quote_ccy: str
    quote_date: str
    base_rate: Decimal
    ingested_at: datetime


class ExchangeRateDailySyncQuote(BaseModel):
    """sync 응답에서 에코하는 일별 값(최소 필드)."""

    quote_date: str
    base_rate: Decimal


class ExchangeRateRangeSyncResponse(BaseModel):
    """Response body for the daily series sync endpoint."""

    source: str
    base_ccy: str
    quote_ccy: str
    start_date: str
    end_date: str
    observed_at: datetime
    affected_count: int
    quotes: list[ExchangeRateDailySyncQuote]