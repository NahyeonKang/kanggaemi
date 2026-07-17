"""
app/schemas/instrument_price.py

통합 시세 스키마 (주식/업종/국내선물옵션 + 해외선물).
  - scraper-layer: ChartResult(ohlcv + 자산군별 스냅샷 + currency).
  - API-layer: OHLCV / valuation / derivative 응답, sync 응답.
"""
from datetime import datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict


# ── scraper-layer ────────────────────────────────────────────
class OhlcvObservation(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    observation_date: str
    open: Optional[Decimal] = None
    high: Optional[Decimal] = None
    low: Optional[Decimal] = None
    close: Optional[Decimal] = None
    volume: Optional[Decimal] = None
    amount: Optional[Decimal] = None


class StockValuationSnapshot(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    name: Optional[str] = None
    current_price: Optional[Decimal] = None
    upper_limit: Optional[Decimal] = None
    lower_limit: Optional[Decimal] = None
    vol_turnover: Optional[Decimal] = None
    listed_shares: Optional[Decimal] = None
    market_cap: Optional[Decimal] = None
    per: Optional[Decimal] = None
    eps: Optional[Decimal] = None
    pbr: Optional[Decimal] = None


class DerivativeSnapshot(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    name: Optional[str] = None
    current_price: Optional[Decimal] = None
    upper_limit: Optional[Decimal] = None
    lower_limit: Optional[Decimal] = None
    basis: Optional[Decimal] = None
    kospi200: Optional[Decimal] = None
    open_interest: Optional[Decimal] = None
    oi_change: Optional[Decimal] = None
    theoretical_price: Optional[Decimal] = None
    disparity: Optional[Decimal] = None
    tick_strength: Optional[Decimal] = None


class ChartResult(BaseModel):
    """스크래퍼 반환: OHLCV + (자산군에 따라) 스냅샷 하나 + currency(해외선물)."""

    model_config = ConfigDict(from_attributes=True)

    source: str = "kis"
    asset_class: str                       # stock | index | future | option | os_future
    entity_code: str
    resolution: str
    observed_at: datetime
    currency: Optional[str] = None         # 해외선물 상품 통화(USD 등)
    observations: list[OhlcvObservation]
    valuation: Optional[StockValuationSnapshot] = None
    derivative: Optional[DerivativeSnapshot] = None


# ── API-layer ────────────────────────────────────────────────
class OhlcvResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    source: str
    asset_class: str
    entity_code: str
    resolution: str
    observation_date: str
    open: Optional[Decimal]
    high: Optional[Decimal]
    low: Optional[Decimal]
    close: Optional[Decimal]
    volume: Optional[Decimal]
    amount: Optional[Decimal]
    currency: Optional[str] = None
    ingested_at: datetime


class StockValuationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    source: str
    ticker: str
    observed_at: datetime
    name: Optional[str]
    current_price: Optional[Decimal]
    upper_limit: Optional[Decimal]
    lower_limit: Optional[Decimal]
    vol_turnover: Optional[Decimal]
    listed_shares: Optional[Decimal]
    market_cap: Optional[Decimal]
    per: Optional[Decimal]
    eps: Optional[Decimal]
    pbr: Optional[Decimal]
    ingested_at: datetime


class DerivativeSnapshotResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    source: str
    entity_code: str
    observed_at: datetime
    name: Optional[str]
    current_price: Optional[Decimal]
    upper_limit: Optional[Decimal]
    lower_limit: Optional[Decimal]
    basis: Optional[Decimal]
    kospi200: Optional[Decimal]
    open_interest: Optional[Decimal]
    oi_change: Optional[Decimal]
    theoretical_price: Optional[Decimal]
    disparity: Optional[Decimal]
    tick_strength: Optional[Decimal]
    ingested_at: datetime


class ChartSyncResponse(BaseModel):
    source: str
    asset_class: str
    entity_code: str
    resolution: str
    ohlcv_affected: int
    snapshot_affected: int
    start_date: Optional[str]
    end_date: Optional[str]
    currency: Optional[str] = None