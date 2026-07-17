from __future__ import annotations

from app.agent.contracts import ClassificationResult, Evidence, FactorFeature
from app.agent.graph import build_investment_report_graph


class FakeResolver:
    def resolve(self, _db, _query):
        return ClassificationResult(
            asset_code="005930", asset_name="삼성전자", asset_class="kr_equity",
            region="kr", market="KOSPI", sector="반도체", currency="KRW",
            aliases=["삼성전자"], horizon="3M", query_intent="general_outlook",
            applicable_dimensions=["macro", "flow", "industry", "valuation"],
            classification_confidence=1.0, cache_hit=True,
        )


class FakeFeatureEngine:
    def compute_factor(self, factor, classification, as_of):
        return FactorFeature(
            factor_id=factor.factor_id, factor_name=factor.factor_name,
            signal="positive", strength=0.5,
            evidence=Evidence(
                data_spec_id=factor.data_spec_id, source="test",
                entity_code=classification["asset_code"], field="value", value=1,
                unit="test", observation_date=as_of, as_of_date=as_of,
                transform=factor.transform, is_estimated=False, caveats=[],
            ),
        )


class RevisingReasoner:
    def __init__(self):
        self.synthesis_calls = 0
        self.evaluation_calls = 0

    def synthesize(self, payload):
        self.synthesis_calls += 1
        return {
            "final_view": {"macro": {"signal": "mixed"}},
            "confidence": {"overall": 70},
            "investment_horizon": "3M", "summary": "근거 기반 조건부 긍정",
            "strategy": {
                "action": "분할 접근", "entry_strategy": "조정 시 분할",
                "position_sizing": "제한적", "risk_control": "손실 한도 설정",
                "review_condition": "핵심 근거 반전",
            },
            "scenario_analysis": {"base": "완만한 개선", "bull": "실적 개선", "bear": "수요 둔화"},
            "key_evidence_ids": ["E1"], "key_risks": ["수요 둔화"],
            "monitoring_indicators": ["E1"], "final_report": "조건부 전략",
        }

    def evaluate(self, _payload):
        self.evaluation_calls += 1
        critical = ["재작성 필요"] if self.evaluation_calls < 3 else []
        return {
            "rubric_scores": {
                "evidence_coverage": 20, "data_freshness": 15,
                "logical_consistency": 20, "risk_awareness": 15,
                "actionability": 15, "overconfidence_control": 10, "user_fit": 5,
            },
            "warnings": [], "critical_issues": critical,
            "improvement_suggestions": critical, "missing_factors": [],
            "revised_summary": "근거와 위험을 함께 반영",
        }


def test_complete_graph_parallel_analysis_revision_loop_and_report():
    reasoner = RevisingReasoner()
    graph = build_investment_report_graph(
        FakeResolver(), reasoner, feature_engine=FakeFeatureEngine(),
    )
    result = graph.invoke({
        "run_id": "report-test", "user_query": "삼성전자 전망",
        "as_of_date": "2026-07-16", "locale": "ko-KR",
    })
    assert reasoner.synthesis_calls == 3
    assert reasoner.evaluation_calls == 3
    assert result["revision_count"] == 2
    assert result["evaluation_result"]["passed"] is True
    assert result["synthesis_result"]["final_view"] == "mixed"
    assert result["synthesis_result"]["confidence"] == 0.7
    assert "투자 전략 리포트" in result["user_facing_report"]
    assert "관점: 혼재" in result["user_facing_report"]
    assert "관점: mixed" not in result["user_facing_report"]
    assert result["notion_report_page"]["run_id"] == "report-test"
