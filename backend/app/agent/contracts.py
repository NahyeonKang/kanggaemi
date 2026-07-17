from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


Signal = Literal["positive", "neutral", "negative", "mixed", "unknown"]
QueryIntent = Literal[
    "buy_or_not", "long_term_outlook", "short_term_timing", "risk_check",
    "portfolio_allocation", "comparison", "general_outlook",
]


class AssetExtraction(BaseModel):
    asset_name: str
    asset_class: str
    horizon: str
    query_intent: QueryIntent
    aliases: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.8, ge=0, le=1)


class ClassificationResult(BaseModel):
    asset_code: str
    asset_name: str
    asset_class: str
    region: str
    market: str
    sector: str | None = None
    currency: str | None = None
    aliases: list[str] = Field(default_factory=list)
    horizon: str
    query_intent: QueryIntent
    applicable_dimensions: list[str]
    classification_confidence: float = Field(ge=0, le=1)
    ambiguity: dict[str, Any] = Field(default_factory=dict)
    cache_hit: bool = False


class SelectedFactor(BaseModel):
    factor_id: str
    factor_name: str
    dimension: str
    data_spec_id: str
    transform: dict[str, Any]
    interpretation: dict[str, str]
    caveats: list[str] = Field(default_factory=list)


class Evidence(BaseModel):
    data_spec_id: str
    source: str
    entity_code: str
    field: str
    value: float
    unit: str
    observation_date: str
    as_of_date: str
    transform: dict[str, Any]
    is_estimated: bool
    caveats: list[str] = Field(default_factory=list)


class FactorFeature(BaseModel):
    factor_id: str
    factor_name: str
    signal: Signal
    strength: float = Field(ge=0, le=1)
    evidence: Evidence | None = None
    caveat: list[str] = Field(default_factory=list)
    missing_reason: str | None = None


class DimensionResult(BaseModel):
    dimension: str
    signal: Signal
    confidence: float = Field(ge=0, le=1)
    summary: str
    key_evidence: list[Evidence]
    risks: list[str]
    missing_data: list[str] = Field(default_factory=list)
    factor_results: list[FactorFeature] = Field(default_factory=list)
    foreign_flow_view: str | None = None
    institution_flow_view: str | None = None
    retail_flow_view: str | None = None
    futures_positioning_view: str | None = None
    program_trading_view: str | None = None
