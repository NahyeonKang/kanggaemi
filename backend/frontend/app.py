from __future__ import annotations

import sys
import types
from datetime import date
from importlib.machinery import ModuleSpec
from pathlib import Path
from typing import Any

BACKEND_DIR = Path(__file__).resolve().parents[1]
backend_path = str(BACKEND_DIR)
# Streamlit prepends the script directory (`frontend/`) to sys.path. Because
# this file is named app.py, `import app.agent` would otherwise resolve this
# file as the top-level `app` module instead of backend/app/. Merely checking
# membership is insufficient when the backend path already exists later.
sys.path[:] = [value for value in sys.path if value != backend_path]
sys.path.insert(0, backend_path)

# backend/app intentionally has no __init__.py and is therefore a namespace
# package. PathFinder prefers the concrete frontend/app.py found later on
# sys.path over that namespace candidate. Register the intended namespace
# explicitly before any lazy backend import.
backend_app_dir = str(BACKEND_DIR / "app")
loaded_app = sys.modules.get("app")
if loaded_app is None or not hasattr(loaded_app, "__path__"):
    backend_app = types.ModuleType("app")
    backend_app.__package__ = "app"
    backend_app.__path__ = [backend_app_dir]
    backend_app.__spec__ = ModuleSpec("app", loader=None, is_package=True)
    backend_app.__spec__.submodule_search_locations = [backend_app_dir]
    sys.modules["app"] = backend_app

import streamlit as st

from frontend.adapters import LangGraphAgentAdapter, MockAgentAdapter
from frontend.adapters.base import AgentEventAdapter
from frontend.config import APP_TITLE, DEFAULT_ADAPTER
from frontend.contracts import NodeEvent
from frontend.pdf import FontConfigurationError, PdfGenerationError, make_pdf_filename, markdown_to_pdf
from frontend.specs import FrontendNodeSpec, FrontendSpecs, load_frontend_specs


@st.cache_resource
def _specs() -> FrontendSpecs:
    return load_frontend_specs()


def _init_state() -> None:
    defaults: dict[str, Any] = {
        "running": False, "run_requested": False, "report_markdown": None,
        "report_payload": None, "pdf_bytes": None, "pdf_filename": None,
        "run_error": None, "active_query": "", "active_as_of": date.today(),
        "node_states": {}, "active_adapter": DEFAULT_ADAPTER,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def _display_name(node: FrontendNodeSpec) -> str:
    labels = {
        "classification": "질의·자산 분류", "planning": "분석 계획",
        "macro": "매크로 분석", "flow": "수급 분석", "industry": "산업 분석",
        "valuation": "밸류에이션 분석", "synthesis": "종합 판단",
        "evaluation": "품질 평가", "formatting": "리포트 작성",
    }
    return labels.get(node.owner_dimension, node.node_name)


def _render_pending(slot: Any, node: FrontendNodeSpec) -> None:
    slot.markdown(f"⬜ **{_display_name(node)}** · 대기")


def _render_event(slot: Any, node: FrontendNodeSpec, event: NodeEvent) -> None:
    name = _display_name(node)
    if event.type == "node_start":
        slot.info(f"⏳ {name} 진행 중")
    elif event.type == "node_complete":
        suffix = f" — {event.summary}" if event.summary else ""
        slot.success(f"✅ {name} 완료{suffix}")
    elif event.type == "error":
        suffix = f" — {event.summary}" if event.summary else ""
        slot.error(f"❌ {name} 실패{suffix}")


def _consume_stream(
    specs: FrontendSpecs, slots: dict[str, Any], adapter: AgentEventAdapter,
) -> None:
    by_id = {node.node_id: node for node in specs.nodes}
    try:
        for event in adapter.stream(
            st.session_state.active_query, st.session_state.active_as_of,
        ):
            event.validate()
            node = by_id.get(event.node_id)
            if node is None:
                raise ValueError(f"node_specs에 없는 이벤트를 받았습니다: {event.node_id}")
            _render_event(slots[event.node_id], node, event)
            if event.type != "final":
                st.session_state.node_states[event.node_id] = event.as_dict()
            if event.type == "error":
                st.session_state.run_error = event.summary or "에이전트 실행 실패"
                return
            if event.type == "final":
                report = (event.payload or {}).get("report_markdown")
                if not isinstance(report, str) or not report.strip():
                    raise ValueError("final 이벤트에 report_markdown이 없습니다.")
                st.session_state.report_markdown = report
                st.session_state.report_payload = event.payload
    except Exception as exc:
        st.session_state.run_error = str(exc)
        st.error(f"에이전트 실행 중 오류가 발생했습니다: {exc}")
    finally:
        st.session_state.running = False
        st.session_state.run_requested = False


def main() -> None:
    st.set_page_config(page_title=APP_TITLE, page_icon="📈", layout="centered")
    _init_state()
    try:
        specs = _specs()
    except Exception as exc:
        st.error(f"node_specs.yaml을 읽지 못했습니다: {exc}")
        st.stop()

    st.title(APP_TITLE)
    with st.sidebar:
        st.header("분석 옵션")
        as_of = st.date_input("기준일 (as_of)", value=date.today(), disabled=st.session_state.running)
        adapter_labels = {
            "langgraph": "실제 에이전트 (LangGraph)",
            "mock": "Mock 데모",
        }
        default_index = 0 if DEFAULT_ADAPTER == "langgraph" else 1
        selected_adapter = st.selectbox(
            "실행 어댑터", options=list(adapter_labels),
            format_func=adapter_labels.__getitem__, index=default_index,
            disabled=st.session_state.running,
        )

    query = st.text_input(
        "분석 질의", placeholder="예: 코스피 한 달 전망을 분석해줘",
        key="query_input", disabled=st.session_state.running,
    )
    clicked = st.button(
        "분석 실행", type="primary", use_container_width=True,
        disabled=st.session_state.running,
    )
    if clicked:
        if not query.strip():
            st.warning("분석 질의를 입력하세요.")
        else:
            st.session_state.running = True
            st.session_state.run_requested = True
            st.session_state.active_query = query.strip()
            st.session_state.active_as_of = as_of
            st.session_state.active_adapter = selected_adapter
            st.session_state.report_markdown = None
            st.session_state.report_payload = None
            st.session_state.pdf_bytes = None
            st.session_state.pdf_filename = None
            st.session_state.run_error = None
            st.session_state.node_states = {}
            st.rerun()

    st.subheader("분석 진행상황")
    slots: dict[str, Any] = {}
    for node in specs.nodes:
        slots[node.node_id] = st.empty()
        stored = st.session_state.node_states.get(node.node_id)
        if stored:
            _render_event(slots[node.node_id], node, NodeEvent.from_mapping(stored))
        else:
            _render_pending(slots[node.node_id], node)

    if st.session_state.run_requested:
        adapter: AgentEventAdapter
        if st.session_state.active_adapter == "langgraph":
            adapter = LangGraphAgentAdapter(specs)
        else:
            adapter = MockAgentAdapter(specs)
        _consume_stream(specs, slots, adapter)
        st.rerun()
    if st.session_state.run_error:
        st.error(f"실행 실패: {st.session_state.run_error}")

    report = st.session_state.report_markdown
    if report:
        st.divider()
        st.subheader("최종 리포트")
        st.markdown(report)
        if st.button("PDF 생성", help="클릭할 때만 PDF를 생성합니다."):
            try:
                with st.spinner("한글 폰트를 포함해 PDF를 생성하고 있습니다..."):
                    st.session_state.pdf_bytes = markdown_to_pdf(report, title="투자 전략 리포트")
                    st.session_state.pdf_filename = make_pdf_filename(st.session_state.active_query)
            except (FontConfigurationError, PdfGenerationError) as exc:
                st.error(str(exc))
        if st.session_state.pdf_bytes:
            st.download_button(
                "PDF 다운로드", data=st.session_state.pdf_bytes,
                file_name=st.session_state.pdf_filename, mime="application/pdf",
                use_container_width=True, on_click="ignore",
            )


if __name__ == "__main__":
    main()
