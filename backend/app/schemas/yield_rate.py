"""
app/schemas/yield_rate.py

금리 도메인 스키마.
  - scraper-layer: BOK 시리즈 / KIS comp-interest (Decimal, observed_at).
  - 내부 record: YieldSnapshotRecord (스냅샷 insert 입력).
  - API-layer: 관측/스냅샷 응답 (resolution, observed_at, ingested_at).
"""
from datetime import datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict


# ── scraper-layer (BOK) ──────────────────────────────────────
class BOKSeriesObservation(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    observation_date: str                  # "YYYY-MM-DD"
    value: Optional[Decimal] = None


class BOKSeriesData(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    source: str = "bok"
    stat_code: str
    item_code: str
    resolution: str = "D"                  # "D" | "M"
    observed_at: datetime
    observations: list[BOKSeriesObservation]


# ── scraper-layer (KIS) ──────────────────────────────────────
class KISCompInterestItem(BaseModel):
    bcdt_code: str
    hts_kor_isnm: str = ""
    bond_mnrt_prpr: Optional[str] = None         # 원시 문자열 (service에서 Decimal 변환)
    prdy_vrss_sign: Optional[str] = None
    bond_mnrt_prdy_vrss: Optional[str] = None
    prdy_ctrt: Optional[str] = None
    stck_bsop_date: str = ""


class KISCompInterestData(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    source: str = "kis"
    observed_at: datetime                  # fetch 시각 (tz-aware)
    output1: list[KISCompInterestItem]


# ── 내부 record (snapshot insert 입력) ───────────────────────
class YieldSnapshotRecord(BaseModel):
    source: str = "kis"
    country: str
    tenor: str
    current_rate: Optional[Decimal] = None
    prdy_vrss_sign: Optional[str] = None
    prdy_vrss: Optional[Decimal] = None
    prdy_ctrt: Optional[Decimal] = None
    base_date: str = ""
    observed_at: datetime


# ── API-layer ────────────────────────────────────────────────
class YieldObservationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    source: str
    country: str
    tenor: str
    resolution: str
    observation_date: str
    close: Optional[Decimal]
    ingested_at: datetime


class YieldSnapshotResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    source: str
    country: str
    tenor: str
    current_rate: Optional[Decimal]
    prdy_vrss_sign: Optional[str]
    prdy_vrss: Optional[Decimal]
    prdy_ctrt: Optional[Decimal]
    base_date: str
    observed_at: datetime
    ingested_at: datetime