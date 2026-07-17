from __future__ import annotations

from typing import Any, TypedDict


class InvestmentAgentState(TypedDict, total=False):
    run_id: str
    user_query: str
    as_of_date: str
    locale: str
    classification: dict[str, Any]
    execution_plan: dict[str, Any]
    selected_dimensions: list[str]
    selected_factors: list[dict[str, Any]]
    node_order: list[str]
    skipped_dimensions: list[dict[str, str]]
    planning_confidence: float
    flow_result: dict[str, Any]
    simple_output: str
