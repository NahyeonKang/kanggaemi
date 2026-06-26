"""
app/schemas/macro_indicator.py

매크로 지표 스키마.
  - scraper-layer: FRED 시리즈 (Decimal, observed_at).
  - API-layer: 관측 응답 / sync 응답 (resolution, ingested_at).
"""
from datetime import datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict


# ── scraper-layer (FRED) ─────────────────────────────────────
class FredObservation(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    observation_date: str                 # "YYYY-MM-DD"
    value: Optional[Decimal] = None        # 결측("." 등)은 None


class FredSeriesData(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    source: str = "fred"
    series_id: str
    observed_at: datetime                  # fetch 시각 (tz-aware)
    observations: list[FredObservation]


# ── API-layer ────────────────────────────────────────────────
class MacroObservationResponse(BaseModel):
    """저장된 관측 1건 (GET). ORM 행에서 직접 매핑."""

    model_config = ConfigDict(from_attributes=True)

    source: str
    series_id: str
    resolution: str
    observation_date: str
    value: Optional[Decimal]
    ingested_at: datetime


class MacroSeriesSyncResult(BaseModel):
    series_id: str
    resolution: str
    affected_count: int
    start_date: Optional[str]
    end_date: Optional[str]


class MacroSyncResponse(BaseModel):
    source: str
    series: list[MacroSeriesSyncResult]