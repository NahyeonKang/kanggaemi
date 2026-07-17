"""
app/schemas/market_funds.py

증시자금 스키마.
  - scraper-layer: 일별 관측 시리즈.
  - API-layer: 관측/sync 응답.
"""
from datetime import datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict


# ── scraper-layer ────────────────────────────────────────────
class MarketFundsObservation(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    observation_date: str                     # "YYYY-MM-DD"
    customer_deposit: Optional[Decimal] = None
    customer_deposit_change: Optional[Decimal] = None
    amount_turnover: Optional[Decimal] = None
    receivable: Optional[Decimal] = None
    credit_loan_balance: Optional[Decimal] = None
    futures_deposit: Optional[Decimal] = None


class MarketFundsSeries(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    source: str = "kis"
    observed_at: datetime
    observations: list[MarketFundsObservation]


# ── API-layer ────────────────────────────────────────────────
class MarketFundsResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    source: str
    observation_date: str
    customer_deposit: Optional[Decimal]
    customer_deposit_change: Optional[Decimal]
    amount_turnover: Optional[Decimal]
    receivable: Optional[Decimal]
    credit_loan_balance: Optional[Decimal]
    futures_deposit: Optional[Decimal]
    ingested_at: datetime


class MarketFundsSyncResponse(BaseModel):
    source: str
    affected_count: int
    start_date: Optional[str]
    end_date: Optional[str]