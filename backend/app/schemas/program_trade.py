"""
app/schemas/program_trade.py

프로그램매매 스키마.
  - scraper-layer: (date × trade_class × account_type) 정규화 시리즈.
  - API-layer: 관측/sync 응답.
"""
from datetime import datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict


# ── scraper-layer ────────────────────────────────────────────
class ProgramTradeObservation(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    observation_date: str                  # "YYYY-MM-DD"
    trade_class: str                       # arbt | nabt | whol
    account_type: str                      # entm | onsl | smtn
    sell_vol: Optional[Decimal] = None
    sell_amount: Optional[Decimal] = None
    buy_vol: Optional[Decimal] = None
    buy_amount: Optional[Decimal] = None
    net_qty: Optional[Decimal] = None
    net_amount: Optional[Decimal] = None


class ProgramTradeSeries(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    source: str = "kis"
    scope: str                             # "market" | "stock"
    entity_code: str                       # KOSPI/KOSDAQ | 티커
    observed_at: datetime
    observations: list[ProgramTradeObservation]


# ── API-layer ────────────────────────────────────────────────
class ProgramTradeResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    source: str
    scope: str
    entity_code: str
    trade_class: str
    account_type: str
    observation_date: str
    sell_vol: Optional[Decimal]
    sell_amount: Optional[Decimal]
    buy_vol: Optional[Decimal]
    buy_amount: Optional[Decimal]
    net_qty: Optional[Decimal]
    net_amount: Optional[Decimal]
    ingested_at: datetime


class ProgramTradeSyncResponse(BaseModel):
    source: str
    scope: str
    entity_code: str
    affected_count: int
    start_date: Optional[str]
    end_date: Optional[str]