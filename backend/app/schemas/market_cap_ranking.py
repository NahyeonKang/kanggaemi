"""
app/schemas/market_cap_ranking.py
"""
from datetime import datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict


# ── scraper-layer ────────────────────────────────────────────
class MarketCapRow(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    rank: int
    ticker: str
    name: Optional[str] = None
    close_price: Optional[Decimal] = None
    volume: Optional[Decimal] = None
    listed_shares: Optional[Decimal] = None
    market_cap: Optional[Decimal] = None
    market_weight: Optional[Decimal] = None


class MarketCapRanking(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    source: str = "kis"
    market: str                                 # kospi|kosdaq|kospi200|all
    observed_at: datetime
    rows: list[MarketCapRow]


# ── API-layer ────────────────────────────────────────────────
class MarketCapResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    source: str
    market: str
    observation_date: str
    rank: int
    ticker: str
    name: Optional[str]
    close_price: Optional[Decimal]
    volume: Optional[Decimal]
    listed_shares: Optional[Decimal]
    market_cap: Optional[Decimal]
    market_weight: Optional[Decimal]
    ingested_at: datetime


class MarketCapSyncResponse(BaseModel):
    source: str
    market: str
    observation_date: str
    affected_count: int
    top_rank: Optional[int]