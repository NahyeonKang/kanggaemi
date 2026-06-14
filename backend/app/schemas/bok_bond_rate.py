"""
app/schemas/bok_bond_rate.py

Pydantic schemas for the BOK (Bank of Korea) ECOS historical bond rate domain.

Scraper-layer schemas (BOKBondRateItem, BOKBondRateData) are used internally
by BOKBondRateScraper and the service layer.

API-layer schemas (BOKBondRateSyncResponse, BOKBondRateResponse) are used
by the FastAPI router.
"""
from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Scraper-layer schemas
# ---------------------------------------------------------------------------


class BOKBondRateItem(BaseModel):
    """Single observation row from the ECOS StatisticSearch API."""

    item_name: str
    observation_date: str   # YYYY-MM-DD
    value: float


class BOKBondRateData(BaseModel):
    """Normalized StatisticSearch result returned by BOKBondRateScraper."""

    source: str = "bok"
    item_code: str
    items: list[BOKBondRateItem] = Field(default_factory=list)
    fetched_at: str


# ---------------------------------------------------------------------------
# API-layer schemas
# ---------------------------------------------------------------------------


class BOKBondRateSyncResponse(BaseModel):
    """Response body for POST /bond-rate/history/treasury-10y/sync."""

    source: str
    item_code: str
    affected_count: int
    start_date: str
    end_date: str


class BOKBondRateResponse(BaseModel):
    """Single bond rate row for GET /bond-rate/history/treasury-10y responses."""

    source: str
    item_code: str
    item_name: str
    observation_date: str
    value: float
    fetched_at: str

    model_config = {"from_attributes": True}
