from __future__ import annotations

from collections import Counter
from typing import Callable

from app.agent.assets import AssetResolver
from app.agent.catalog import load_yaml
from app.agent.contracts import DimensionResult, SelectedFactor
from app.agent.feature_engine import FeatureEngine
from app.agent.state import InvestmentAgentState
from app.db.session import SessionLocal


def make_classify_node(resolver: AssetResolver) -> Callable[[InvestmentAgentState], dict]:
    def classify_node(state: InvestmentAgentState) -> dict:
        with SessionLocal() as db:
            result = resolver.resolve(db, state["user_query"])
        return {"classification": result.model_dump()}

    return classify_node


def plan_node(state: InvestmentAgentState) -> dict:
    classification = state["classification"]
    if "flow" not in classification["applicable_dimensions"]:
        raise ValueError(
            f"flow dimension is not applicable to {classification['asset_class']}"
        )
    selected: list[SelectedFactor] = []
    for factor in load_yaml("factor_catalog.yaml")["factors"]:
        if factor.get("status") != "active":
            continue
        if factor.get("dimension") != "flow":
            continue
        if classification["asset_class"] not in factor.get("asset_classes", []):
            continue
        data_spec_ids = factor.get("data_spec_ids") or []
        if not data_spec_ids:
            continue
        selected.append(SelectedFactor(
            factor_id=factor["factor_id"],
            factor_name=factor["factor_name"],
            dimension="flow",
            data_spec_id=data_spec_ids[0],
            transform=dict(factor.get("transform") or {"method": "level", "window": None}),
            interpretation=dict(factor.get("interpretation") or {}),
            caveats=list(factor.get("caveats") or []),
        ))
    if not selected:
        raise ValueError("NO_FACTOR_FOUND: no active flow factor for asset_class")
    values = [factor.model_dump() for factor in selected]
    return {
        "execution_plan": {"flow_node": [factor.factor_id for factor in selected]},
        "selected_dimensions": ["flow"],
        "selected_factors": values,
        "node_order": ["flow_node"],
        "skipped_dimensions": [
            {"dimension": value, "reason": "outside thin vertical slice"}
            for value in classification["applicable_dimensions"] if value != "flow"
        ],
        "planning_confidence": 1.0,
    }


def make_analyzer(
    dimension: str, feature_engine: FeatureEngine
) -> Callable[[InvestmentAgentState], dict]:
    if dimension != "flow":
        raise ValueError(f"thin slice only supports flow analyzer, got: {dimension}")

    def analyzer(state: InvestmentAgentState) -> dict:
        classification = state["classification"]
        factors = [
            SelectedFactor.model_validate(value)
            for value in state["selected_factors"]
            if value["dimension"] == dimension
        ]
        features = [
            feature_engine.compute_factor(
                factor, classification, state["as_of_date"]
            )
            for factor in factors
        ]
        available = [feature for feature in features if feature.evidence is not None]
        missing = [
            f"{feature.factor_id}: {feature.missing_reason}"
            for feature in features if feature.evidence is None
        ]
        signal = _aggregate_signal([feature.signal for feature in available])
        confidence = (
            len(available) / len(features) * 0.8
            if features else 0.0
        )
        if any(feature.evidence and feature.evidence.is_estimated for feature in available):
            confidence *= 0.85
        by_id = {feature.factor_id: feature for feature in features}
        result = DimensionResult(
            dimension="flow",
            signal=signal,
            confidence=round(confidence, 4),
            summary=_summary(classification["asset_name"], available, signal),
            key_evidence=[feature.evidence for feature in available if feature.evidence],
            risks=[
                "수급 데이터는 가격 방향의 원인이 아니라 단기 매매 압력으로 해석해야 합니다.",
                "당일 가집계 데이터는 익영업일 확정 과정에서 정정될 수 있습니다.",
            ],
            missing_data=missing,
            factor_results=features,
            foreign_flow_view=_view(by_id.get("FLOW_FOREIGN_SPOT")),
            institution_flow_view=_view(by_id.get("FLOW_INSTITUTION_SPOT")),
            retail_flow_view=_view(by_id.get("FLOW_INDIVIDUAL_SPOT")),
            program_trading_view=_view(by_id.get("PROGRAM_NET")),
        )
        return {"flow_result": result.model_dump()}

    return analyzer


def simple_output_node(state: InvestmentAgentState) -> dict:
    classification = state["classification"]
    flow = state["flow_result"]
    lines = [
        f"[{classification['asset_name']}({classification['asset_code']}) 수급 분석]",
        f"기준일: {state['as_of_date']}",
        f"신호: {flow['signal']} / 신뢰도: {flow['confidence']:.2f}",
        flow["summary"],
        "근거:",
    ]
    for evidence in flow["key_evidence"]:
        lines.append(
            f"- {evidence['data_spec_id']} {evidence['field']}="
            f"{evidence['value']:.2f} {evidence['unit']} "
            f"({evidence['observation_date']}, {evidence['transform']['method']})"
        )
    if flow["missing_data"]:
        lines.append("누락: " + "; ".join(flow["missing_data"]))
    return {"simple_output": "\n".join(lines)}


def _aggregate_signal(signals: list[str]) -> str:
    if not signals:
        return "unknown"
    counts = Counter(signals)
    positive, negative = counts["positive"], counts["negative"]
    if positive and negative:
        return "mixed"
    if positive:
        return "positive"
    if negative:
        return "negative"
    return "neutral"


def _summary(asset_name: str, features: list, signal: str) -> str:
    if not features:
        return f"{asset_name}의 as-of 수급 근거가 없어 판단을 보류합니다."
    facts = ", ".join(
        f"{feature.factor_name} {feature.evidence.value:.2f} {feature.evidence.unit}"
        for feature in features if feature.evidence
    )
    return (
        f"{asset_name}의 5영업일 수급은 {signal} 신호입니다. {facts}. "
        "이는 단기 매매 압력이며 독립적인 가격 예측으로 해석하지 않습니다."
    )


def _view(feature) -> str | None:
    if feature is None:
        return None
    if feature.evidence is None:
        return f"데이터 없음: {feature.missing_reason}"
    return (
        f"{feature.signal}: {feature.evidence.value:.2f} "
        f"{feature.evidence.unit} ({feature.evidence.observation_date})"
    )
