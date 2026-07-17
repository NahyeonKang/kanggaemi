from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from frontend.config import NODE_SPECS_PATH


@dataclass(frozen=True)
class FrontendNodeSpec:
    node_id: str
    node_name: str
    owner_dimension: str


@dataclass(frozen=True)
class FrontendSpecs:
    nodes: tuple[FrontendNodeSpec, ...]
    report_sections: tuple[str, ...]


def load_frontend_specs(path: Path = NODE_SPECS_PATH) -> FrontendSpecs:
    with path.open(encoding="utf-8") as file:
        data = yaml.safe_load(file)
    if not isinstance(data, dict):
        raise ValueError(f"node specs must be a mapping: {path}")
    raw_nodes = [node for node in data.get("nodes", []) if node.get("status") == "active"]
    if not raw_nodes:
        raise ValueError("node_specs.yaml has no active nodes")
    ordered_ids = _stable_execution_order(raw_nodes, data.get("execution_graph") or {})
    by_id = {node["node_id"]: node for node in raw_nodes}
    nodes = tuple(FrontendNodeSpec(
        node_id=node_id, node_name=str(by_id[node_id]["node_name"]),
        owner_dimension=str(by_id[node_id].get("owner_dimension") or node_id),
    ) for node_id in ordered_ids)
    synthesize = next(
        (node for node in raw_nodes if node["node_id"] == "synthesize_node"), None
    )
    sections = tuple((synthesize or {}).get("recommended_report_structure") or [])
    if not sections or not all(isinstance(value, str) and value.strip() for value in sections):
        raise ValueError("synthesize_node.recommended_report_structure is required")
    return FrontendSpecs(nodes=nodes, report_sections=sections)


def _stable_execution_order(nodes: list[dict[str, Any]], graph: dict[str, Any]) -> list[str]:
    ids = [node["node_id"] for node in nodes]
    position = {value: index for index, value in enumerate(ids)}
    edges = list(graph.get("edges") or [])
    # Only the forward evaluator branch belongs in the display sequence. The
    # revision edge deliberately points backward and would create a cycle.
    edges.extend(
        edge for edge in graph.get("conditional_edges") or []
        if edge.get("to") in position and edge.get("from") in position
        and position[edge["from"]] < position[edge["to"]]
    )
    outgoing = {value: set() for value in ids}
    indegree = {value: 0 for value in ids}
    for edge in edges:
        source, target = edge.get("from"), edge.get("to")
        if source not in position or target not in position or target in outgoing[source]:
            continue
        outgoing[source].add(target)
        indegree[target] += 1
    ready = [value for value in ids if indegree[value] == 0]
    ordered: list[str] = []
    while ready:
        ready.sort(key=position.__getitem__)
        current = ready.pop(0)
        ordered.append(current)
        for target in sorted(outgoing[current], key=position.__getitem__):
            indegree[target] -= 1
            if indegree[target] == 0:
                ready.append(target)
    if len(ordered) != len(ids):
        raise ValueError("execution_graph contains an unexpected forward cycle")
    return ordered
