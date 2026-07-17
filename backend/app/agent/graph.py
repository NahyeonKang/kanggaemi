from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from app.agent.assets import AssetResolver
from app.agent.feature_engine import FeatureEngine
from app.agent.nodes import make_analyzer, make_classify_node, plan_node, simple_output_node
from app.agent.nodes import (
    evaluation_route, make_evaluate_node, make_synthesize_node, report_format_node,
)
from app.agent.reasoning import ReportReasoner
from app.agent.state import InvestmentAgentState


def build_flow_slice_graph(
    resolver: AssetResolver,
    feature_engine: FeatureEngine | None = None,
    checkpointer=None,
):
    engine = feature_engine or FeatureEngine()
    builder = StateGraph(InvestmentAgentState)
    builder.add_node("classify_node", make_classify_node(resolver))
    builder.add_node("plan_node", plan_node)
    builder.add_node("flow_node", make_analyzer("flow", engine))
    builder.add_node("simple_output_node", simple_output_node)
    builder.add_edge(START, "classify_node")
    builder.add_edge("classify_node", "plan_node")
    builder.add_edge("plan_node", "flow_node")
    builder.add_edge("flow_node", "simple_output_node")
    builder.add_edge("simple_output_node", END)
    return builder.compile(checkpointer=checkpointer)


def build_investment_report_graph(
    resolver: AssetResolver,
    reasoner: ReportReasoner,
    feature_engine: FeatureEngine | None = None,
    checkpointer=None,
):
    engine = feature_engine or FeatureEngine()
    builder = StateGraph(InvestmentAgentState)
    builder.add_node("classify_node", make_classify_node(resolver))
    builder.add_node("plan_node", plan_node)
    for dimension in ("macro", "flow", "industry", "valuation"):
        builder.add_node(f"{dimension}_node", make_analyzer(dimension, engine))
    builder.add_node("synthesize_node", make_synthesize_node(reasoner))
    builder.add_node("evaluate_node", make_evaluate_node(reasoner))
    builder.add_node("report_formatter_node", report_format_node)
    builder.add_edge(START, "classify_node")
    builder.add_edge("classify_node", "plan_node")
    analyzers = [f"{value}_node" for value in ("macro", "flow", "industry", "valuation")]
    for node in analyzers:
        builder.add_edge("plan_node", node)
    builder.add_edge(analyzers, "synthesize_node")
    builder.add_edge("synthesize_node", "evaluate_node")
    builder.add_conditional_edges(
        "evaluate_node", evaluation_route,
        {
            "synthesize_node": "synthesize_node",
            "report_formatter_node": "report_formatter_node",
        },
    )
    builder.add_edge("report_formatter_node", END)
    return builder.compile(checkpointer=checkpointer)
