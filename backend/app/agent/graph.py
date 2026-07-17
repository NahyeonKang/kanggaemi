from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from app.agent.assets import AssetResolver
from app.agent.feature_engine import FeatureEngine
from app.agent.nodes import make_analyzer, make_classify_node, plan_node, simple_output_node
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
