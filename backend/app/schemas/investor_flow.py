"""
app/schemas/investor_flow.py

수급(투자자별 매매동향) 스키마.
  - scraper-layer: 시장/종목 공통으로 (date × investor_type) 정규화 시리즈.
  - API-layer: 관측 응답 / sync 응답.
"""
from datetime import datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict


# ── scraper-layer ────────────────────────────────────────────
class InvestorFlowObservation(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    observation_date: str                  # "YYYY-MM-DD"
    investor_type: str
    net_qty: Optional[Decimal] = None
    net_amount: Optional[Decimal] = None    # 백만원


class InvestorFlowSeries(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    source: str = "kis"
    scope: str                              # "market" | "stock"
    market: str                             # "KOSPI" | "KOSDAQ"
    entity_code: str                        # 업종코드 | 티커
    observed_at: datetime
    observations: list[InvestorFlowObservation]


# ── API-layer ────────────────────────────────────────────────
class InvestorFlowResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    source: str
    scope: str
    market: str
    entity_code: str
    investor_type: str
    observation_date: str
    net_qty: Optional[Decimal]
    net_amount: Optional[Decimal]
    ingested_at: datetime


class InvestorFlowSyncResponse(BaseModel):
    source: str
    scope: str
    market: str
    entity_code: str
    affected_count: int
    investor_types: list[str]
    start_date: Optional[str]
    end_date: Optional[str]