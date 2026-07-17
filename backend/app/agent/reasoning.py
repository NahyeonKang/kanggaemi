from __future__ import annotations

import json
from typing import Any, Protocol

from openai import OpenAI

from app.agent.catalog import load_yaml
from app.core.config import settings


class ReportReasoner(Protocol):
    def synthesize(self, payload: dict[str, Any]) -> dict[str, Any]: ...
    def evaluate(self, payload: dict[str, Any]) -> dict[str, Any]: ...


class OpenAIReportReasoner:
    """LLM reasoning boundary; evidence values remain grounded by node code."""

    def __init__(self, client: OpenAI | None = None, model: str | None = None) -> None:
        if not settings.OPENAI_API_KEY and client is None:
            raise RuntimeError("OPENAI_API_KEY is required for report reasoning")
        self.client = client or OpenAI(api_key=settings.OPENAI_API_KEY)
        self.model = model or settings.LLM_MODEL

    def synthesize(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._json_call(
            """You synthesize a Korean investment strategy report from supplied point-in-time
dimension results. Never invent facts, values, tickers, or evidence. key_evidence_ids must
only contain IDs listed in evidence_registry. Reconcile conflicting dimensions, lower
confidence for missing data, and make conclusions conditional rather than personalized
financial advice. Return JSON with final_view, confidence (0..1), investment_horizon,
summary, strategy {action,entry_strategy,position_sizing,risk_control,review_condition},
scenario_analysis {base,bull,bear}, key_evidence_ids, key_risks,
monitoring_indicators, final_report. Every human-readable prose value MUST be written in
Korean. Keep only contract enums, evidence IDs, factor IDs, data-spec IDs, ticker codes,
units, and proper nouns in their original form. Do not write English prose.""",
            payload,
        )

    def evaluate(self, payload: dict[str, Any]) -> dict[str, Any]:
        specs = load_yaml("node_specs.yaml")
        rubric = next(
            item["evaluation_rubric"] for item in specs["nodes"]
            if item["node_id"] == "evaluate_node"
        )
        return self._json_call(
            """Audit the supplied investment synthesis. Use only supplied data. Return JSON
with rubric_scores using exactly evidence_coverage, data_freshness,
logical_consistency, risk_awareness, actionability, overconfidence_control, user_fit;
warnings, critical_issues, improvement_suggestions, missing_factors, revised_summary.
Scores must respect the provided rubric maxima. A critical contradiction or unsupported
conclusion belongs in critical_issues. Every warning, issue, suggestion, and summary MUST
be Korean; keep only contract keys, enums, IDs, codes, units, and proper nouns unchanged.""",
            {**payload, "evaluation_rubric": rubric},
        )

    def _json_call(self, system_prompt: str, payload: dict[str, Any]) -> dict[str, Any]:
        response = self.client.chat.completions.create(
            model=self.model,
            temperature=0,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": json.dumps(payload, ensure_ascii=False, default=str)},
            ],
        )
        content = response.choices[0].message.content
        if not content:
            raise ValueError("LLM returned an empty report reasoning response")
        value = json.loads(content)
        if not isinstance(value, dict):
            raise ValueError("LLM report reasoning response must be an object")
        return value
