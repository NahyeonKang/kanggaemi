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
    macro_result: dict[str, Any]
    flow_result: dict[str, Any]
    industry_result: dict[str, Any]
    valuation_result: dict[str, Any]
    synthesis_result: dict[str, Any]
    evaluation_result: dict[str, Any]
    evaluation_feedback: list[str]
    revision_count: int
    max_synthesis_revisions: int
    user_facing_report: str
    notion_report_page: dict[str, Any]
    report_run_summary: dict[str, Any]
    tags: list[str]
    simple_output: str
