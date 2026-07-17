"""
app/schemas/stock_financials.py
"""
from datetime import datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict


# ── scraper-layer ────────────────────────────────────────────
class FinancialsObservation(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    stac_yymm: str                              # "YYYYMM"
    revenue_growth: Optional[Decimal] = None
    op_income_growth: Optional[Decimal] = None
    net_income_growth: Optional[Decimal] = None
    roe: Optional[Decimal] = None
    eps: Optional[Decimal] = None
    net_profit_margin: Optional[Decimal] = None
    ev_ebitda: Optional[Decimal] = None
    revenue: Optional[Decimal] = None
    op_income: Optional[Decimal] = None


class FinancialsSeries(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    source: str = "kis"
    ticker: str
    period_type: str                            # "annual" | "quarter"
    observed_at: datetime
    observations: list[FinancialsObservation]


# ── API-layer ────────────────────────────────────────────────
class FinancialsResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    source: str
    ticker: str
    period_type: str
    stac_yymm: str
    revenue_growth: Optional[Decimal]
    op_income_growth: Optional[Decimal]
    net_income_growth: Optional[Decimal]
    roe: Optional[Decimal]
    eps: Optional[Decimal]
    net_profit_margin: Optional[Decimal]
    ev_ebitda: Optional[Decimal]
    revenue: Optional[Decimal]
    op_income: Optional[Decimal]
    ingested_at: datetime


class FinancialsSyncResponse(BaseModel):
    source: str
    ticker: str
    period_type: str
    affected_count: int
    start_yymm: Optional[str]
    end_yymm: Optional[str]