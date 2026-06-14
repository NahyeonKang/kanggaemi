"""
app/schemas/yield_rate.py

Pydantic schemas for the yield domain (interest rates), split by
time-resolution:
  - yield_daily    : official daily close yields, sourced from FRED (US) and
                      BOK (KR)
  - yield_snapshot : latest KIS comp-interest snapshot, one row per
                      (country, tenor)

Scraper-layer schemas (BOKSeries*, KISCompInterest*) are used internally by
BOKScraper / KISScraper and the yield service. FRED scraper output reuses
FredSeriesData / FredObservation from app.schemas.macro_indicator, since
fred_scraper.fetch_series is shared by both the macro and yield domains.

API-layer schemas are used by the FastAPI routers.
"""
from typing import Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Scraper-layer schemas
# ---------------------------------------------------------------------------


class BOKSeriesObservation(BaseModel):
    """Single daily observation returned by BOKScraper.fetch_series."""

    observation_date: str           # YYYY-MM-DD
    value: Optional[float] = None


class BOKSeriesData(BaseModel):
    """Normalized ECOS StatisticSearch result returned by BOKScraper."""

    source: str = "bok"
    stat_code: str
    item_code: str
    observations: list[BOKSeriesObservation] = Field(default_factory=list)
    fetched_at: str


class KISCompInterestItem(BaseModel):
    """Single bond rate row from the KIS comp-interest output1."""

    bcdt_code: str                              # 자료코드
    hts_kor_isnm: str                           # HTS한글종목명
    bond_mnrt_prpr: str                         # 채권금리현재가
    prdy_vrss_sign: Optional[str] = None        # 전일대비부호
    bond_mnrt_prdy_vrss: Optional[str] = None   # 채권금리전일대비
    prdy_ctrt: Optional[str] = None             # 전일대비율
    stck_bsop_date: str                         # 주식영업일자 (YYYYMMDD)


class KISCompInterestData(BaseModel):
    """Normalized comp-interest result returned by KISScraper."""

    source: str = "kis"
    output1: list[KISCompInterestItem] = Field(default_factory=list)
    fetched_at: str


# ---------------------------------------------------------------------------
# Persistence-layer schema
# ---------------------------------------------------------------------------


class YieldSnapshotRecord(BaseModel):
    """A single normalized yield_snapshot row ready for persistence."""

    country: str
    tenor: str
    current_rate: Optional[float] = None
    prdy_vrss_sign: Optional[str] = None
    prdy_vrss: Optional[float] = None
    prdy_ctrt: Optional[float] = None
    base_date: str          # YYYYMMDD
    source: str = "kis"
    fetched_at: str         # ISO datetime string


# ---------------------------------------------------------------------------
# API-layer schemas — yield_daily
# ---------------------------------------------------------------------------


class YieldDailySyncRequest(BaseModel):
    """Request body for POST /yield/daily/sync."""

    country: str    # 'KR' / 'US'
    tenor: str       # '10Y', '3Y', '30Y', 'SOFR', '2Y', 'KOFR', 'CD91', 'CORP3Y_AA'


class YieldDailySyncResponse(BaseModel):
    """Response body for POST /yield/daily/sync."""

    country: str
    tenor: str
    source: str
    affected_count: int
    start_date: Optional[str] = None
    end_date: Optional[str] = None


class YieldDailySyncAllResponse(BaseModel):
    """Response body for POST /yield/daily/sync-all."""

    results: list[YieldDailySyncResponse] = Field(default_factory=list)


class YieldDailyResponse(BaseModel):
    """Single daily yield observation for GET /yield/daily responses."""

    country: str
    tenor: str
    d: str                       # YYYY-MM-DD
    close: Optional[float] = None
    source: str
    ingested_at: str

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# API-layer schemas — yield_snapshot
# ---------------------------------------------------------------------------


class YieldSnapshotSyncResponse(BaseModel):
    """Response body for POST /yield/snapshot/sync."""

    source: str
    affected_count: int
    tenors: list[str] = Field(default_factory=list)


class YieldSnapshotResponse(BaseModel):
    """Single latest snapshot for GET /yield/snapshot responses."""

    country: str
    tenor: str
    current_rate: Optional[float] = None
    prdy_vrss_sign: Optional[str] = None
    prdy_vrss: Optional[float] = None
    prdy_ctrt: Optional[float] = None
    base_date: Optional[str] = None
    source: str
    fetched_at: str

    model_config = {"from_attributes": True}
