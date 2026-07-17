from __future__ import annotations

import uuid
from contextlib import contextmanager
from datetime import date
from typing import Any, Callable, ContextManager, Iterator

from frontend.contracts import NodeEvent
from frontend.specs import FrontendNodeSpec, FrontendSpecs, load_frontend_specs


RuntimeFactory = Callable[[], ContextManager[Any]]


class LangGraphAgentAdapter:
    """Translate the backend LangGraph task stream into the frontend contract."""

    def __init__(
        self,
        specs: FrontendSpecs | None = None,
        *,
        setup_checkpointer: bool = False,
        runtime_factory: RuntimeFactory | None = None,
    ) -> None:
        self.specs = specs or load_frontend_specs()
        self.setup_checkpointer = setup_checkpointer
        self.runtime_factory = runtime_factory or self._runtime

    def stream(self, query: str, as_of_date: date) -> Iterator[NodeEvent]:
        by_id = {node.node_id: node for node in self.specs.nodes}
        run_id = str(uuid.uuid4())
        config = {"configurable": {"thread_id": run_id}}
        initial_state = {
            "run_id": run_id,
            "user_query": query,
            "as_of_date": as_of_date.isoformat(),
            "locale": "ko-KR",
        }
        observed: set[str] = set()
        current = self.specs.nodes[0]
        final_state: dict[str, Any] = {}
        try:
            with self.runtime_factory() as graph:
                for task in graph.stream(
                    initial_state, config, stream_mode="tasks",
                ):
                    if not isinstance(task, dict):
                        continue
                    node = by_id.get(str(task.get("name", "")))
                    if node is None:
                        continue
                    current = node
                    observed.add(node.node_id)
                    if _is_task_start(task):
                        yield NodeEvent(
                            type="node_start", node_id=node.node_id,
                            node_name=node.node_name, status="running",
                        )
                        continue
                    error = task.get("error")
                    if error:
                        yield NodeEvent(
                            type="error", node_id=node.node_id,
                            node_name=node.node_name, status="failed",
                            summary=_error_text(error),
                            payload={"run_id": run_id, "mode": "langgraph"},
                        )
                        return
                    update = _task_result(task.get("result"))
                    yield NodeEvent(
                        type="node_complete", node_id=node.node_id,
                        node_name=node.node_name, status="done",
                        summary=_completion_summary(node, update),
                    )
                    final_state.update(update)

                snapshot = graph.get_state(config)
                values = getattr(snapshot, "values", None)
                if isinstance(values, dict):
                    final_state = values

            # A backend graph may temporarily omit a newly declared UI node.
            # Show that node through the mock contract without replacing actual results.
            for node in self.specs.nodes:
                if node.node_id in observed:
                    continue
                yield NodeEvent(
                    type="node_start", node_id=node.node_id,
                    node_name=node.node_name, status="running",
                    summary="현재 백엔드 그래프에 없어 Mock으로 표시합니다.",
                )
                yield NodeEvent(
                    type="node_complete", node_id=node.node_id,
                    node_name=node.node_name, status="done",
                    summary="준비되지 않은 노드의 Mock 단계입니다.",
                    payload={"fallback": "mock"},
                )

            report = final_state.get("user_facing_report")
            if not isinstance(report, str) or not report.strip():
                raise ValueError("LangGraph 최종 state에 user_facing_report가 없습니다.")
            terminal = by_id.get("report_formatter_node", self.specs.nodes[-1])
            yield NodeEvent(
                type="final", node_id=terminal.node_id,
                node_name=terminal.node_name, status="done",
                summary="실제 에이전트 리포트 작성이 완료됐습니다.",
                payload={
                    "report_markdown": report,
                    "query": query,
                    "as_of_date": as_of_date.isoformat(),
                    "run_id": run_id,
                    "mode": "langgraph",
                    "report_run_summary": final_state.get("report_run_summary"),
                },
            )
        except Exception as exc:
            yield NodeEvent(
                type="error", node_id=current.node_id, node_name=current.node_name,
                status="failed", summary=_error_text(exc),
                payload={"run_id": run_id, "mode": "langgraph"},
            )

    @contextmanager
    def _runtime(self) -> Iterator[Any]:
        # Imports stay behind the adapter boundary so Mock mode does not require
        # agent, OpenAI, PostgreSQL, or LangGraph dependencies.
        from langgraph.checkpoint.postgres import PostgresSaver

        from app.agent.assets import AssetResolver
        from app.agent.graph import build_investment_report_graph
        from app.agent.llm import OpenAIAssetExtractor
        from app.agent.reasoning import OpenAIReportReasoner
        from app.core.config import settings

        uri = _postgres_uri(settings.DATABASE_URL)
        resolver = AssetResolver(OpenAIAssetExtractor())
        reasoner = OpenAIReportReasoner()
        with PostgresSaver.from_conn_string(uri) as saver:
            if self.setup_checkpointer:
                saver.setup()
            yield build_investment_report_graph(
                resolver, reasoner, checkpointer=saver,
            )


def _is_task_start(task: dict[str, Any]) -> bool:
    return "input" in task and "result" not in task and "error" not in task


def _task_result(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    root = value.get("__root__")
    return root if isinstance(root, dict) else value


def _completion_summary(node: FrontendNodeSpec, update: dict[str, Any]) -> str:
    if node.node_id == "classify_node":
        value = update.get("classification") or {}
        return _short(f"{value.get('asset_name', '자산')} ({value.get('asset_code', '-')}) 분류 완료")
    if node.node_id == "plan_node":
        factors = update.get("selected_factors") or []
        dimensions = update.get("selected_dimensions") or []
        return f"{len(dimensions)}개 차원, {len(factors)}개 팩터 선정"
    if node.owner_dimension in {"macro", "flow", "industry", "valuation"}:
        value = update.get(f"{node.owner_dimension}_result") or {}
        return _short(str(value.get("summary") or f"{node.owner_dimension} 분석 완료"))
    if node.node_id == "synthesize_node":
        return _short(str((update.get("synthesis_result") or {}).get("summary") or "종합 판단 완료"))
    if node.node_id == "evaluate_node":
        value = update.get("evaluation_result") or {}
        passed = "통과" if value.get("passed") else "재검토"
        return f"평가 {value.get('evaluation_score', '-')}점 · {passed}"
    if node.node_id == "report_formatter_node":
        return "최종 Markdown 리포트 생성 완료"
    return "노드 처리 완료"


def _short(value: str, limit: int = 160) -> str:
    compact = " ".join(value.split())
    return compact if len(compact) <= limit else compact[: limit - 1] + "…"


def _error_text(error: Any) -> str:
    value = _short(str(error), 300)
    return value or "알 수 없는 에이전트 오류"


def _postgres_uri(value: str) -> str:
    if not value.startswith("postgresql"):
        raise ValueError("실제 에이전트의 PostgresSaver에는 PostgreSQL DATABASE_URL이 필요합니다.")
    return value.replace("postgresql+psycopg2://", "postgresql://", 1)
