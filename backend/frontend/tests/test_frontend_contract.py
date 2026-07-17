from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from types import SimpleNamespace
from contextlib import contextmanager

import pytest

from frontend.adapters.mock import MockAgentAdapter
from frontend.adapters.langgraph import LangGraphAgentAdapter
from frontend.contracts import NodeEvent
from frontend.pdf import FontConfigurationError, make_pdf_filename, validate_font
from frontend.specs import load_frontend_specs


def test_specs_follow_execution_graph_and_report_contract() -> None:
    specs = load_frontend_specs()
    assert [node.node_id for node in specs.nodes] == [
        "classify_node", "plan_node", "macro_node", "flow_node",
        "industry_node", "valuation_node", "synthesize_node",
        "evaluate_node", "report_formatter_node",
    ]
    assert specs.report_sections == (
        "질문 재정의", "결론 요약", "투자기간", "핵심 근거",
        "차원별 분석 요약", "상승 시나리오", "하락 시나리오",
        "투자전략", "리스크 및 모니터링 지표", "신뢰도와 한계",
    )


def test_mock_stream_and_markdown_use_yaml_order() -> None:
    specs = load_frontend_specs()
    events = list(MockAgentAdapter(specs, delay_seconds=0).stream(
        "코스피 전망", date(2026, 7, 16),
    ))
    assert len(events) == len(specs.nodes) * 2 + 1
    assert [event.node_id for event in events[::2][:-1]] == [
        node.node_id for node in specs.nodes
    ]
    final = events[-1]
    final.validate()
    markdown = final.payload["report_markdown"]
    positions = [markdown.index(f"## {section}") for section in specs.report_sections]
    assert positions == sorted(positions)


def test_final_event_requires_payload() -> None:
    event = NodeEvent("final", "report", "Report", "done")
    with pytest.raises(ValueError, match="payload"):
        event.validate()


def test_font_error_and_safe_filename(tmp_path: Path) -> None:
    with pytest.raises(FontConfigurationError, match="한글 폰트"):
        validate_font(tmp_path / "missing.ttf")
    assert make_pdf_filename(
        "코스피: 한달/전망?", datetime(2026, 7, 18, 5, 0, 0),
    ) == "코스피_한달전망_20260718_050000.pdf"


def test_langgraph_task_events_are_adapted_to_node_events() -> None:
    specs = load_frontend_specs()

    class FakeGraph:
        def stream(self, initial_state, config, stream_mode):
            assert stream_mode == "tasks"
            for node in specs.nodes:
                yield {"id": node.node_id, "name": node.node_id, "input": initial_state}
                update = {}
                if node.node_id == "report_formatter_node":
                    update = {"user_facing_report": "# 실제 리포트"}
                yield {
                    "id": node.node_id, "name": node.node_id,
                    "error": None, "result": update, "interrupts": [],
                }

        def get_state(self, config):
            return SimpleNamespace(values={
                "user_facing_report": "# 실제 리포트",
                "report_run_summary": {"final_view": "neutral"},
            })

    @contextmanager
    def runtime():
        yield FakeGraph()

    events = list(LangGraphAgentAdapter(
        specs, runtime_factory=runtime,
    ).stream("코스피 전망", date(2026, 7, 16)))
    assert events[0].type == "node_start"
    assert events[-1].type == "final"
    assert events[-1].payload["report_markdown"] == "# 실제 리포트"
    assert events[-1].payload["mode"] == "langgraph"
    assert not any(event.type == "error" for event in events)
