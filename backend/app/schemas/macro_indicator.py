"""
app/schemas/macro_indicator.py

Pydantic schemas for the macro indicator domain.

Scraper-layer schemas (FredObservation, FredSeriesData) are used internally
by FredMacroScraper and the service layer.

API-layer schemas (MacroSyncResponse, MacroObservationResponse) are used
by the FastAPI router.
"""
from typing import Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Scraper-layer schemas
# ---------------------------------------------------------------------------


class FredObservation(BaseModel):
    """Single FRED observation returned by the scraper."""

    source: str = "fred"
    series_id: str
    observation_date: str   # YYYY-MM-DD
    value: Optional[float] = None
    fetched_at: str         # ISO datetime string


class FredSeriesData(BaseModel):
    """Collection of FRED observations for one series."""

    source: str = "fred"
    series_id: str
    observations: list[FredObservation] = Field(default_factory=list)
    fetched_at: str


# ---------------------------------------------------------------------------
# API-layer schemas
# ---------------------------------------------------------------------------


class MacroSyncResponseItem(BaseModel):
    """Per-series result for POST /macro/us-rates/sync."""

    series_id: str
    affected_count: int
    start_date: Optional[str] = None
    end_date: Optional[str] = None


class MacroSyncResponse(BaseModel):
    """Response body for POST /macro/us-rates/sync."""

    source: str
    series: list[MacroSyncResponseItem]


class MacroObservationResponse(BaseModel):
    """Single observation for GET /macro/series responses."""

    source: str
    series_id: str
    observation_date: str
    value: Optional[float] = None
    fetched_at: str

    model_config = {"from_attributes": True}
