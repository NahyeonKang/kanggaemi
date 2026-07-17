from __future__ import annotations

import html
import time
from datetime import date
from typing import Iterator

from frontend.config import MOCK_DELAY_SECONDS
from frontend.contracts import NodeEvent
from frontend.specs import FrontendSpecs, load_frontend_specs


class MockAgentAdapter:
    """Agent-free event source implementing the same contract as a real adapter."""

    def __init__(
        self, specs: FrontendSpecs | None = None, delay_seconds: float = MOCK_DELAY_SECONDS,
    ) -> None:
        self.specs = specs or load_frontend_specs()
        self.delay_seconds = max(0.0, delay_seconds)

    def stream(self, query: str, as_of_date: date) -> Iterator[NodeEvent]:
        for node in self.specs.nodes:
            yield NodeEvent(
                type="node_start", node_id=node.node_id, node_name=node.node_name,
                status="running",
            )
            if self.delay_seconds:
                time.sleep(self.delay_seconds)
            yield NodeEvent(
                type="node_complete", node_id=node.node_id, node_name=node.node_name,
                status="done", summary=_node_summary(node.owner_dimension),
            )
        markdown = build_mock_report(query, as_of_date, self.specs.report_sections)
        terminal = self.specs.nodes[-1]
        yield NodeEvent(
            type="final", node_id=terminal.node_id, node_name=terminal.node_name,
            status="done", summary="최종 리포트 작성이 완료됐습니다.",
            payload={
                "report_markdown": markdown,
                "query": query,
                "as_of_date": as_of_date.isoformat(),
                "mode": "mock",
            },
        )


def build_mock_report(query: str, as_of_date: date, sections: tuple[str, ...]) -> str:
    safe_query = html.escape(query.strip())
    lines = [
        "# 투자 전략 리포트", "",
        f"- 분석 질의: {safe_query}",
        f"- 기준일: {as_of_date.isoformat()}",
        "- 실행 모드: Mock", "",
    ]
    for index, section in enumerate(sections, start=1):
        lines.extend([
            f"## {section}", "",
            _mock_section_body(index, safe_query, as_of_date), "",
        ])
    return "\n".join(lines).strip()


def _node_summary(owner_dimension: str) -> str:
    labels = {
        "classification": "질의에서 분석 자산과 의도를 분류했습니다.",
        "planning": "적용 가능한 분석 차원과 팩터를 선정했습니다.",
        "macro": "금리·환율·유동성 환경을 점검했습니다.",
        "flow": "투자자별 수급과 프로그램 흐름을 점검했습니다.",
        "industry": "산업 사이클과 관련 지표를 점검했습니다.",
        "valuation": "밸류에이션과 실적 지표를 점검했습니다.",
        "synthesis": "차원별 결과를 종합했습니다.",
        "evaluation": "근거와 위험을 기준으로 초안을 평가했습니다.",
        "formatting": "리포트 스키마에 맞춰 결과를 정리했습니다.",
    }
    return labels.get(owner_dimension, "노드 처리를 완료했습니다.")


def _mock_section_body(index: int, query: str, as_of_date: date) -> str:
    return (
        f"{index}번째 계약 섹션의 Mock 내용입니다. `{query}` 질의를 "
        f"{as_of_date.isoformat()} 기준으로 분석한 결과가 실제 어댑터 연결 후 표시됩니다."
    )
