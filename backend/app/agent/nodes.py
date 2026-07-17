from __future__ import annotations

from collections import Counter
from typing import Any, Callable

from app.agent.assets import AssetResolver
from app.agent.catalog import load_yaml
from app.agent.contracts import (
    DimensionResult, EvaluationResult, ReportOutput, SelectedFactor,
    SynthesisResult,
)
from app.agent.feature_engine import FeatureEngine
from app.agent.reasoning import ReportReasoner
from app.agent.state import InvestmentAgentState
from app.db.session import SessionLocal


DIMENSIONS = ("macro", "flow", "industry", "valuation")
RESULT_KEYS = {value: f"{value}_result" for value in DIMENSIONS}


def make_classify_node(resolver: AssetResolver) -> Callable[[InvestmentAgentState], dict]:
    def classify_node(state: InvestmentAgentState) -> dict:
        with SessionLocal() as db:
            result = resolver.resolve(db, state["user_query"])
        return {"classification": result.model_dump()}

    return classify_node


def plan_node(state: InvestmentAgentState) -> dict:
    classification = state["classification"]
    applicable = set(classification["applicable_dimensions"])
    selected: list[SelectedFactor] = []
    execution_plan: dict[str, list[str]] = {f"{value}_node": [] for value in DIMENSIONS}
    for factor in load_yaml("factor_catalog.yaml")["factors"]:
        dimension = factor.get("dimension")
        if factor.get("status") != "active" or dimension not in applicable:
            continue
        if classification["asset_class"] not in factor.get("asset_classes", []):
            continue
        data_spec_ids = factor.get("data_spec_ids") or []
        if not data_spec_ids and factor.get("data_spec_id"):
            data_spec_ids = [factor["data_spec_id"]]
        if not data_spec_ids:
            continue
        item = SelectedFactor(
            factor_id=factor["factor_id"], factor_name=factor["factor_name"],
            dimension=dimension, data_spec_id=data_spec_ids[0],
            transform=dict(factor.get("transform") or {"method": "level", "window": None}),
            interpretation=dict(factor.get("interpretation") or {}),
            caveats=list(factor.get("caveats") or []),
        )
        selected.append(item)
        execution_plan[f"{dimension}_node"].append(item.factor_id)
    if not selected:
        raise ValueError(
            f"NO_FACTOR_FOUND: no active factor for {classification['asset_class']}"
        )
    selected_dimensions = [
        value for value in DIMENSIONS if execution_plan[f"{value}_node"]
    ]
    skipped = [
        {"dimension": value, "reason": (
            "not applicable to asset class" if value not in applicable
            else "no active grounded factor in factor_catalog"
        )}
        for value in DIMENSIONS if value not in selected_dimensions
    ]
    return {
        "execution_plan": execution_plan,
        "selected_dimensions": selected_dimensions,
        "selected_factors": [factor.model_dump() for factor in selected],
        "node_order": [f"{value}_node" for value in selected_dimensions],
        "skipped_dimensions": skipped,
        "planning_confidence": 1.0,
        "revision_count": 0,
        "max_synthesis_revisions": int(
            load_yaml("node_specs.yaml")["conventions"]["max_synthesis_revisions"]
        ),
    }


def make_analyzer(
    dimension: str, feature_engine: FeatureEngine
) -> Callable[[InvestmentAgentState], dict]:
    if dimension not in DIMENSIONS:
        raise ValueError(f"unsupported analyzer dimension: {dimension}")

    def analyzer(state: InvestmentAgentState) -> dict:
        classification = state["classification"]
        factors = [
            SelectedFactor.model_validate(value)
            for value in state["selected_factors"] if value["dimension"] == dimension
        ]
        if not factors:
            result = DimensionResult(
                dimension=dimension, signal="unknown", confidence=0,
                summary=f"{dimension} 차원에 적용 가능한 active 팩터가 없습니다.",
                key_evidence=[], risks=[],
                missing_data=["no active applicable factor"], factor_results=[],
            )
            return {RESULT_KEYS[dimension]: result.model_dump()}
        features = [
            feature_engine.compute_factor(factor, classification, state["as_of_date"])
            for factor in factors
        ]
        available = [feature for feature in features if feature.evidence is not None]
        missing = [
            f"{feature.factor_id}: {feature.missing_reason}"
            for feature in features if feature.evidence is None
        ]
        signal = _aggregate_signal([feature.signal for feature in available])
        confidence = len(available) / len(features) * 0.8
        if any(feature.evidence and feature.evidence.is_estimated for feature in available):
            confidence *= 0.85
        by_id = {feature.factor_id: feature for feature in features}
        result = DimensionResult(
            dimension=dimension, signal=signal, confidence=round(confidence, 4),
            summary=_summary(dimension, classification["asset_name"], available, signal),
            key_evidence=[feature.evidence for feature in available if feature.evidence],
            risks=_dimension_risks(dimension), missing_data=missing,
            factor_results=features, **_dimension_views(dimension, by_id),
        )
        return {RESULT_KEYS[dimension]: result.model_dump()}

    return analyzer


def make_synthesize_node(reasoner: ReportReasoner) -> Callable[[InvestmentAgentState], dict]:
    def synthesize_node(state: InvestmentAgentState) -> dict:
        dimension_results = {
            value: state[RESULT_KEYS[value]] for value in DIMENSIONS
            if RESULT_KEYS[value] in state
        }
        evidence = [
            item for result in dimension_results.values()
            for item in result.get("key_evidence", [])
        ]
        registry = {f"E{index + 1}": item for index, item in enumerate(evidence)}
        draft = reasoner.synthesize({
            "user_query": state["user_query"],
            "as_of_date": state["as_of_date"],
            "classification": state["classification"],
            "execution_plan": state["execution_plan"],
            "dimension_results": dimension_results,
            "evidence_registry": registry,
            "revision_count": state.get("revision_count", 0),
            "evaluation_feedback": state.get("evaluation_feedback", []),
        })
        selected_evidence = [
            registry[value] for value in draft.get("key_evidence_ids", [])
            if value in registry
        ]
        if not selected_evidence:
            selected_evidence = evidence[:8]
        result = SynthesisResult(
            final_view=_normalize_final_view(
                draft.get("final_view"), dimension_results
            ),
            confidence=_normalize_confidence(
                draft.get("confidence"), dimension_results
            ),
            investment_horizon=_string_value(
                draft.get("investment_horizon"),
                state["classification"]["horizon"],
            ),
            summary=_korean_text(
                draft.get("summary"), "분석 근거가 부족하여 판단을 보류합니다."
            ),
            strategy=_strategy_contract(draft.get("strategy")),
            scenario_analysis=_scenario_contract(draft.get("scenario_analysis")),
            key_evidence=selected_evidence,
            key_risks=_korean_list(
                draft.get("key_risks"), "정량 근거의 시차와 누락 가능성을 점검해야 합니다."
            ),
            monitoring_indicators=_korean_list(
                draft.get("monitoring_indicators"), "선정 팩터의 최신 관측치를 점검합니다."
            ),
            final_report=_korean_text(
                draft.get("final_report"),
                _korean_text(draft.get("summary"), "분석 근거가 부족합니다."),
            ),
        )
        revised = state.get("revision_count", 0)
        if state.get("evaluation_feedback"):
            revised += 1
        return {"synthesis_result": result.model_dump(), "revision_count": revised}

    return synthesize_node


def make_evaluate_node(reasoner: ReportReasoner) -> Callable[[InvestmentAgentState], dict]:
    def evaluate_node(state: InvestmentAgentState) -> dict:
        synthesis = state["synthesis_result"]
        factors = state["selected_factors"]
        dimension_results = {
            value: state[RESULT_KEYS[value]] for value in DIMENSIONS
            if RESULT_KEYS[value] in state
        }
        raw = reasoner.evaluate({
            "user_query": state["user_query"], "as_of_date": state["as_of_date"],
            "classification": state["classification"],
            "selected_factors": factors, "dimension_results": dimension_results,
            "synthesis": synthesis,
        })
        maxima = {
            "evidence_coverage": 20, "data_freshness": 15,
            "logical_consistency": 20, "risk_awareness": 15,
            "actionability": 15, "overconfidence_control": 10, "user_fit": 5,
        }
        provided = raw.get("rubric_scores") or {}
        rubric = {
            key: max(0, min(maximum, _safe_int(provided.get(key, 0))))
            for key, maximum in maxima.items()
        }
        available = sum(
            len(result.get("key_evidence", [])) for result in dimension_results.values()
        )
        coverage_cap = round(20 * available / max(1, len(factors)))
        rubric["evidence_coverage"] = min(rubric["evidence_coverage"], coverage_cap)
        critical = _korean_list(
            raw.get("critical_issues"), "분석 논리의 핵심 문제를 수정해야 합니다."
        )
        if not synthesis.get("key_evidence"):
            critical.append("최종 판단을 뒷받침하는 point-in-time evidence가 없습니다.")
        score = sum(rubric.values())
        passed = score >= 70 and not critical
        result = EvaluationResult(
            evaluation_score=score, passed=passed, rubric_scores=rubric,
            warnings=_korean_list(raw.get("warnings"), "평가 경고를 확인해야 합니다."),
            critical_issues=critical,
            improvement_suggestions=_korean_list(
                raw.get("improvement_suggestions"), "근거와 위험 설명을 보강해야 합니다."
            ),
            missing_factors=[str(value) for value in raw.get("missing_factors", [])],
            revised_summary=_korean_text(raw.get("revised_summary"), ""),
        )
        feedback = result.critical_issues + result.improvement_suggestions
        return {
            "evaluation_result": result.model_dump(),
            "evaluation_feedback": feedback,
        }

    return evaluate_node


def evaluation_route(state: InvestmentAgentState) -> str:
    evaluation = state["evaluation_result"]
    if evaluation["passed"]:
        return "report_formatter_node"
    if state.get("revision_count", 0) >= state.get("max_synthesis_revisions", 2):
        return "report_formatter_node"
    return "synthesize_node"


def report_format_node(state: InvestmentAgentState) -> dict:
    classification = state["classification"]
    synthesis = state["synthesis_result"]
    evaluation = state["evaluation_result"]
    lines = [
        f"# {classification['asset_name']} 투자 전략 리포트",
        "", f"- 기준일: {state['as_of_date']}",
        f"- 관점: {_signal_ko(synthesis['final_view'])}",
        f"- 신뢰도: {synthesis['confidence']:.0%}",
        f"- 투자기간: {synthesis['investment_horizon']}", "",
        "## 결론", "", synthesis["summary"], "",
        "## 전략", "",
        f"- 행동: {synthesis['strategy']['action']}",
        f"- 진입: {synthesis['strategy']['entry_strategy']}",
        f"- 비중: {synthesis['strategy']['position_sizing']}",
        f"- 위험관리: {synthesis['strategy']['risk_control']}",
        f"- 재검토 조건: {synthesis['strategy']['review_condition']}", "",
        "## 시나리오", "",
        f"- 기본: {synthesis['scenario_analysis']['base']}",
        f"- 상승: {synthesis['scenario_analysis']['bull']}",
        f"- 하락: {synthesis['scenario_analysis']['bear']}", "",
        "## 근거", "",
    ]
    for item in synthesis["key_evidence"]:
        lines.append(
            f"- `{item['data_spec_id']}` {item['entity_code']} {item['field']}="
            f"{item['value']:.4g} {item['unit']} ({item['observation_date']})"
        )
    lines.extend(["", "## 주요 위험", ""])
    lines.extend(f"- {value}" for value in synthesis["key_risks"])
    lines.extend([
        "", "## 품질 평가", "",
        f"- 점수: {evaluation['evaluation_score']}/100",
        f"- 통과: {'예' if evaluation['passed'] else '아니오(수정 상한 도달)'}",
        f"- 재작성 횟수: {state.get('revision_count', 0)}",
    ])
    if evaluation["warnings"]:
        lines.extend(f"- 경고: {value}" for value in evaluation["warnings"])
    lines.extend(["", "> 본 리포트는 적재 데이터 기반 분석이며 개인화된 투자 자문이 아닙니다."])
    user_report = "\n".join(lines)
    output = ReportOutput(
        user_facing_report=user_report,
        notion_report_page={
            "title": f"{classification['asset_name']} - {state['as_of_date']}",
            "run_id": state["run_id"], "classification": classification,
            "execution_plan": state["execution_plan"],
            "dimension_results": {
                value: state[RESULT_KEYS[value]] for value in DIMENSIONS
            },
            "synthesis": synthesis, "evaluation": evaluation,
        },
        report_run_summary={
            "run_id": state["run_id"], "asset_code": classification["asset_code"],
            "as_of_date": state["as_of_date"], "final_view": synthesis["final_view"],
            "confidence": synthesis["confidence"],
            "evaluation_score": evaluation["evaluation_score"],
            "revision_count": state.get("revision_count", 0),
        },
        tags=[classification["asset_class"], classification["market"], synthesis["final_view"]],
    )
    return output.model_dump()


def simple_output_node(state: InvestmentAgentState) -> dict:
    classification, flow = state["classification"], state["flow_result"]
    lines = [
        f"[{classification['asset_name']}({classification['asset_code']}) 수급 분석]",
        f"기준일: {state['as_of_date']}",
        f"신호: {_signal_ko(flow['signal'])} / 신뢰도: {flow['confidence']:.2f}",
        flow["summary"], "근거:",
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
    if counts["positive"] and counts["negative"]:
        return "mixed"
    if counts["positive"]:
        return "positive"
    if counts["negative"]:
        return "negative"
    return "neutral"


def _summary(dimension: str, asset_name: str, features: list, signal: str) -> str:
    dimension_name = {
        "macro": "거시환경", "flow": "수급", "industry": "산업",
        "valuation": "밸류에이션",
    }[dimension]
    if not features:
        return f"{asset_name}의 {dimension_name} 차원은 기준시점 근거가 없어 판단을 보류합니다."
    facts = ", ".join(
        f"{item.factor_name} {item.evidence.value:.2f} {item.evidence.unit}"
        for item in features[:6] if item.evidence
    )
    return f"{asset_name}의 {dimension_name} 신호는 {_signal_ko(signal)}입니다. 핵심 관측치는 {facts}입니다."


def _view(feature) -> str | None:
    if feature is None:
        return None
    if feature.evidence is None:
        return f"데이터 없음: {feature.missing_reason}"
    return (
        f"{_signal_ko(feature.signal)}: {feature.evidence.value:.2f} "
        f"{feature.evidence.unit} ({feature.evidence.observation_date})"
    )


def _first_view(by_id: dict, ids: tuple[str, ...]) -> str | None:
    return next((_view(by_id[value]) for value in ids if value in by_id), None)


def _dimension_views(dimension: str, by_id: dict) -> dict[str, str | None]:
    if dimension == "flow":
        return {
            "foreign_flow_view": _view(by_id.get("FLOW_FOREIGN_SPOT")),
            "institution_flow_view": _view(by_id.get("FLOW_INSTITUTION_SPOT")),
            "retail_flow_view": _view(by_id.get("FLOW_INDIVIDUAL_SPOT")),
            "futures_positioning_view": _first_view(by_id, ("FUTURES_OI", "FUTURES_BASIS")),
            "program_trading_view": _view(by_id.get("PROGRAM_NET")),
        }
    if dimension == "macro":
        return {
            "rate_view": _first_view(by_id, tuple(value for value in by_id if value.startswith("RATE_"))),
            "fx_view": _view(by_id.get("MACRO_FX_USDKRW")),
            "liquidity_view": _first_view(by_id, ("LIQ_DEPOSIT", "LIQ_CREDIT")),
            "volatility_view": _first_view(by_id, ("VOL_VKOSPI", "VOL_VIX")),
            "commodity_view": _first_view(by_id, tuple(value for value in by_id if value.startswith("CMDT_"))),
        }
    if dimension == "industry":
        return {"cycle_view": _view(by_id.get("SOX_INDEX")), "demand_supply_view": None,
                "peer_view": None, "sector_relative_view": None}
    return {
        "absolute_valuation_view": _first_view(by_id, ("VAL_PER", "VAL_PBR", "VAL_EV_EBITDA")),
        "relative_valuation_view": None,
        "earnings_revision_view": _first_view(by_id, ("VAL_EPS", "VAL_OP_GROWTH", "VAL_NET_GROWTH")),
        "historical_band_view": _first_view(by_id, ("VAL_PER", "VAL_PBR", "VAL_EV_EBITDA")),
    }


def _dimension_risks(dimension: str) -> list[str]:
    return {
        "macro": ["거시지표 발표 시차와 자산별 민감도 차이를 함께 고려해야 합니다."],
        "flow": ["수급은 가격 방향의 원인이 아니라 단기 압력으로 해석해야 합니다."],
        "industry": ["업종 지표를 개별 기업의 실적으로 과대 일반화할 수 있습니다."],
        "valuation": ["낮은 배수는 실적 훼손이 반영된 value trap일 수 있습니다."],
    }[dimension]


def _strategy_contract(value: Any) -> dict[str, str]:
    source = value if isinstance(value, dict) else {}
    return {key: _korean_text(source.get(key), "근거 보강 후 재검토") for key in (
        "action", "entry_strategy", "position_sizing", "risk_control", "review_condition"
    )}


def _scenario_contract(value: Any) -> dict[str, str]:
    source = value if isinstance(value, dict) else {}
    return {key: _korean_text(source.get(key), "근거 부족") for key in ("base", "bull", "bear")}


def _normalize_final_view(value: Any, dimension_results: dict[str, dict]) -> str:
    allowed = {"positive", "neutral", "negative", "mixed", "unknown"}
    if isinstance(value, str) and value in allowed:
        return value
    signals: list[str] = []
    if isinstance(value, dict):
        for key in ("overall", "final_view", "signal"):
            candidate = value.get(key)
            if isinstance(candidate, str) and candidate in allowed:
                return candidate
        for item in value.values():
            if isinstance(item, dict) and item.get("signal") in allowed:
                signals.append(item["signal"])
            elif isinstance(item, str) and item in allowed:
                signals.append(item)
    if not signals:
        signals = [
            result.get("signal", "unknown") for result in dimension_results.values()
        ]
    meaningful = [item for item in signals if item not in {"unknown", "neutral"}]
    if "mixed" in meaningful or ({"positive", "negative"} <= set(meaningful)):
        return "mixed"
    if meaningful:
        return meaningful[0]
    if "neutral" in signals:
        return "neutral"
    return "unknown"


def _normalize_confidence(value: Any, dimension_results: dict[str, dict]) -> float:
    if isinstance(value, dict):
        value = value.get("overall", value.get("confidence"))
    try:
        result = float(value)
    except (TypeError, ValueError):
        confidences = [
            float(item.get("confidence", 0)) for item in dimension_results.values()
        ]
        result = sum(confidences) / len(confidences) if confidences else 0.0
    if result > 1 and result <= 100:
        result /= 100
    return max(0.0, min(1.0, result))


def _string_value(value: Any, fallback: str) -> str:
    return value if isinstance(value, str) and value.strip() else fallback


def _safe_int(value: Any) -> int:
    if isinstance(value, dict):
        value = value.get("score", 0)
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return 0


def _korean_text(value: Any, fallback: str) -> str:
    if isinstance(value, str) and any("가" <= char <= "힣" for char in value):
        return value
    return fallback


def _korean_list(value: Any, fallback: str) -> list[str]:
    if not isinstance(value, list):
        return []
    return [_korean_text(item, fallback) for item in value]


def _signal_ko(value: str) -> str:
    return {
        "positive": "긍정", "neutral": "중립", "negative": "부정",
        "mixed": "혼재", "unknown": "판단 보류",
    }.get(value, "판단 보류")
