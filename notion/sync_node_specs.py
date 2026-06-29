from __future__ import annotations

import argparse
import copy
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

if __package__:
    from .client import (
        NotionClient,
        changed_properties,
        code_block,
        extract_property_value,
        find_database_property,
        heading_2,
        paragraph,
        property_payload,
        property_values_equal,
        rich_text,
        title,
        title_property_name,
        to_plain_value,
    )
else:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from client import (  # type: ignore[no-redef]
        NotionClient,
        changed_properties,
        code_block,
        extract_property_value,
        find_database_property,
        heading_2,
        paragraph,
        property_payload,
        property_values_equal,
        rich_text,
        title,
        title_property_name,
        to_plain_value,
    )


ROOT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_YAML_PATH = "core/node_specs.yaml"
DEFAULT_DATABASE_KEY = "node_specs"
CODE_CHUNK_SIZE = 1800
APPEND_BATCH_SIZE = 80
MANUAL_NOTES_HEADING = "Manual Notes"

PROPERTY_MAPPING: dict[str, tuple[str, str, list[str]]] = {
    "node_id": ("node_id", "title", ["node_id", "node id", "nodeid"]),
    "node_name": ("node_name", "rich_text", ["node_name", "node name", "nodename"]),
    "status": ("status", "select", ["status"]),
    "node_type": ("node_type", "select", ["node_type", "node type", "nodetype"]),
    "stage": ("stage", "number", ["stage"]),
    "owner_dimension": ("owner_dimension", "select", ["owner_dimension", "owner dimension", "ownerdimension"]),
    "description": ("description", "rich_text", ["description"]),
    "depends_on": ("depends_on", "multi_select", ["depends_on", "depends on", "dependson"]),
    "downstream_nodes": ("downstream_nodes", "multi_select", ["downstream_nodes", "downstream nodes", "downstreamnodes"]),
    "expected_data_specs": ("expected_data_specs", "multi_select", ["expected_data_specs", "expected data specs", "expecteddataspecs"]),
}

REQUIRED_WARNING_FIELDS = [
    "node_name",
    "status",
    "node_type",
    "stage",
    "owner_dimension",
]

CODE_SECTION_KEYS = {
    "input_schema",
    "output_schema",
    "failure_modes",
    "retry_policy",
    "quality_checks",
}

LIST_SECTION_KEYS = {
    "process_steps",
    "prompt_guidelines",
}

BODY_SECTIONS: list[tuple[str, str]] = [
    ("Description", "description"),
    ("Dependencies", "dependencies"),
    ("Input Schema", "input_schema"),
    ("Output Schema", "output_schema"),
    ("References", "references"),
    ("Expected Data Specs", "expected_data_specs"),
    ("Process Steps", "process_steps"),
    ("Analysis Rules", "analysis_rules"),
    ("Synthesis Rules", "synthesis_rules"),
    ("Factor Selection Rules", "factor_selection_rules"),
    ("Evaluation Rubric", "evaluation_rubric"),
    ("Recommended Report Structure", "recommended_report_structure"),
    ("Formatting Rules", "formatting_rules"),
    ("Failure Modes", "failure_modes"),
    ("Retry Policy", "retry_policy"),
    ("Quality Checks", "quality_checks"),
    ("Prompt Guidelines", "prompt_guidelines"),
]

BLOCK_KEYS = {
    "paragraph",
    "heading_1",
    "heading_2",
    "heading_3",
    "bulleted_list_item",
    "numbered_list_item",
    "to_do",
    "toggle",
    "quote",
    "callout",
    "code",
    "divider",
}


@dataclass
class SyncCounts:
    created: int = 0
    updated: int = 0
    deprecated: int = 0
    skipped: int = 0
    warnings: list[str] = field(default_factory=list)

    @property
    def warning_count(self) -> int:
        return len(self.warnings)

    def warn(self, message: str) -> None:
        self.warnings.append(message)
        print(f"warning: {message}", file=sys.stderr)


def resolve_yaml_path(value: str) -> Path:
    path = Path(value)
    candidates = [path if path.is_absolute() else ROOT_DIR / path]

    if not path.is_absolute() and len(path.parts) >= 2 and path.parts[0] == "core":
        candidates.append(ROOT_DIR / "backend" / "app" / path)
        if path.name == "node_specs.yaml":
            candidates.append(ROOT_DIR / "backend" / "app" / path.with_name("node_specs.yaml"))

    for candidate in candidates:
        if candidate.exists():
            return candidate

    return candidates[0]


def get_nested(obj: dict[str, Any], path: str, default: Any = None) -> Any:
    current: Any = obj
    for part in path.split("."):
        if not isinstance(current, dict) or part not in current:
            return default
        current = current[part]
    return current


def as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def yaml_dump(value: Any) -> str:
    if value in (None, [], {}):
        return ""
    return yaml.safe_dump(value, allow_unicode=True, sort_keys=False).strip()


def load_node_specs(path: Path, warnings: list[str]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    try:
        with path.open("r", encoding="utf-8") as file:
            data = yaml.safe_load(file)
    except yaml.YAMLError as exc:
        raise ValueError(f"Failed to parse YAML {path}: {exc}") from exc

    nodes = data.get("nodes") if isinstance(data, dict) else None
    if not isinstance(nodes, list):
        raise ValueError(f"{path} must contain a top-level 'nodes' list.")

    seen: set[str] = set()
    for index, node in enumerate(nodes, start=1):
        node_id = node.get("node_id") if isinstance(node, dict) else None
        if not node_id:
            raise ValueError(f"nodes[{index}] must include node_id.")
        if node_id in seen:
            raise ValueError(f"Duplicate node_id in YAML: {node_id}")
        seen.add(node_id)

        for field_name in REQUIRED_WARNING_FIELDS:
            if node.get(field_name) in (None, ""):
                warnings.append(f"{node_id}: missing recommended field '{field_name}'.")

        node.setdefault("depends_on", [])
        node.setdefault("downstream_nodes", [])
        node.setdefault("expected_data_specs", [])

    validate_execution_graph(data, nodes, warnings)
    return nodes, data


def validate_execution_graph(data: dict[str, Any], nodes: list[dict[str, Any]], warnings: list[str]) -> None:
    node_ids = {node["node_id"] for node in nodes}
    graph = data.get("execution_graph", {}) if isinstance(data, dict) else {}
    edges = graph.get("edges", []) if isinstance(graph, dict) else []

    if isinstance(edges, list):
        for edge in edges:
            if not isinstance(edge, dict):
                warnings.append("execution_graph.edges contains a non-object edge.")
                continue
            from_node = edge.get("from")
            to_node = edge.get("to")
            if from_node not in node_ids:
                warnings.append(f"execution_graph edge references missing from node: {from_node}")
            if to_node not in node_ids:
                warnings.append(f"execution_graph edge references missing to node: {to_node}")
    elif edges:
        warnings.append("execution_graph.edges must be a list.")

    for node in nodes:
        node_id = node["node_id"]
        for dependency in as_list(node.get("depends_on")):
            if dependency not in node_ids:
                warnings.append(f"{node_id}: depends_on references missing node: {dependency}")
        for downstream in as_list(node.get("downstream_nodes")):
            if downstream not in node_ids:
                warnings.append(f"{node_id}: downstream_nodes references missing node: {downstream}")


def schema_property(
    available_properties: dict[str, Any],
    notion_name: str,
    expected_type: str,
    aliases: list[str],
    warnings: list[str],
) -> str | None:
    property_name = find_database_property(available_properties, aliases)
    if not property_name:
        warnings.append(f"Missing Notion property '{notion_name}'; skipped.")
        return None

    actual_type = available_properties[property_name]["type"]
    if actual_type != expected_type:
        warnings.append(
            f"Notion property '{property_name}' has type '{actual_type}', expected '{expected_type}'; skipped."
        )
        return None

    return property_name


def build_properties(
    node: dict[str, Any],
    available_properties: dict[str, Any],
    warnings: list[str] | None = None,
) -> dict[str, Any]:
    warnings = warnings if warnings is not None else []
    properties: dict[str, Any] = {}

    for notion_name, (source_path, expected_type, aliases) in PROPERTY_MAPPING.items():
        property_name = schema_property(
            available_properties,
            notion_name,
            expected_type,
            aliases,
            warnings,
        )
        if not property_name:
            continue

        value = get_nested(node, source_path, "")
        if expected_type == "multi_select":
            value = as_list(value)
        elif value is None:
            value = ""

        payload = property_payload(expected_type, value)
        if payload is not None:
            properties[property_name] = payload

    title_property = title_property_name(available_properties)
    if title_property not in properties:
        properties[title_property] = title(node["node_id"])

    return properties


def yaml_code_blocks(value: Any, language: str = "yaml", chunk_size: int = CODE_CHUNK_SIZE) -> list[dict[str, Any]]:
    dumped = yaml_dump(value)
    if not dumped:
        return []
    return [
        code_block(dumped[index : index + chunk_size], language)
        for index in range(0, len(dumped), chunk_size)
    ]


def bullet_item(text: Any) -> dict[str, Any]:
    return {
        "object": "block",
        "type": "bulleted_list_item",
        "bulleted_list_item": {"rich_text": rich_text(to_plain_value(text))},
    }


def dependencies_value(node: dict[str, Any]) -> dict[str, Any]:
    return {
        "depends_on": as_list(node.get("depends_on")),
        "downstream_nodes": as_list(node.get("downstream_nodes")),
    }


def section_value(node: dict[str, Any], key: str) -> Any:
    if key == "dependencies":
        return dependencies_value(node)
    return node.get(key)


def append_section(children: list[dict[str, Any]], heading: str, key: str, value: Any) -> None:
    if value in (None, "", [], {}):
        return

    children.append(heading_2(heading))

    if key in CODE_SECTION_KEYS:
        children.extend(yaml_code_blocks(value))
        return

    if key in LIST_SECTION_KEYS and isinstance(value, list):
        for item in value:
            children.append(bullet_item(item))
        return

    if isinstance(value, str):
        children.append(paragraph(value))
        return

    if isinstance(value, list):
        if all(isinstance(item, str) for item in value):
            for item in value:
                children.append(bullet_item(item))
        else:
            children.extend(yaml_code_blocks(value))
        return

    if isinstance(value, dict):
        children.extend(yaml_code_blocks(value))
        return

    children.append(paragraph(to_plain_value(value)))


def build_page_children(node: dict[str, Any]) -> list[dict[str, Any]]:
    children: list[dict[str, Any]] = []
    for heading, key in BODY_SECTIONS:
        append_section(children, heading, key, section_value(node, key))

    children.append(heading_2(MANUAL_NOTES_HEADING))
    children.append(paragraph(""))
    return children


def strip_null_values(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: strip_null_values(item)
            for key, item in value.items()
            if item is not None
        }
    if isinstance(value, list):
        return [strip_null_values(item) for item in value]
    return value


def clone_appendable_block(block: dict[str, Any]) -> dict[str, Any] | None:
    block_type = block.get("type")
    if not block_type or block_type not in BLOCK_KEYS or block_type not in block:
        return None

    payload = copy.deepcopy(block[block_type])
    for key in ("is_toggleable", "children"):
        payload.pop(key, None)
    payload = strip_null_values(payload)

    return {"object": "block", "type": block_type, block_type: payload}


def block_plain_text(block: dict[str, Any]) -> str:
    block_type = block.get("type")
    if not block_type or block_type not in block:
        return ""

    rich_text_items = block[block_type].get("rich_text", [])
    return "".join(item.get("plain_text", "") for item in rich_text_items)


def preserved_manual_blocks(existing_blocks: list[dict[str, Any]], warnings: list[str]) -> list[dict[str, Any]]:
    manual_start: int | None = None
    for index, block in enumerate(existing_blocks):
        if MANUAL_NOTES_HEADING in block_plain_text(block):
            manual_start = index
            break

    if manual_start is None:
        return []

    preserved: list[dict[str, Any]] = []
    for block in existing_blocks[manual_start:]:
        cloned = clone_appendable_block(block)
        if cloned:
            preserved.append(cloned)
        else:
            warnings.append("Skipped preserving one unsupported Manual Notes block type.")

    return preserved


def append_blocks_in_batches(client: NotionClient, page_id: str, children: list[dict[str, Any]]) -> None:
    for index in range(0, len(children), APPEND_BATCH_SIZE):
        client.append_blocks(page_id, children[index : index + APPEND_BATCH_SIZE])


def replace_page_children_preserving_manual_notes(
    client: NotionClient,
    page_id: str,
    generated_children: list[dict[str, Any]],
    warnings: list[str],
) -> None:
    existing_blocks = client.list_block_children(page_id)
    manual_blocks = preserved_manual_blocks(existing_blocks, warnings)

    if manual_blocks:
        generated_children = generated_children[:-2] + manual_blocks

    # Append first, archive old blocks only after append succeeds. This avoids
    # losing the existing body when Notion rejects a copied Manual Notes block.
    append_blocks_in_batches(client, page_id, generated_children)

    for block in existing_blocks:
        client.archive_block(block["id"])


def page_node_id(page: dict[str, Any], node_id_property: str) -> str:
    page_property = page.get("properties", {}).get(node_id_property)
    if not page_property:
        return ""

    value = extract_property_value(page_property)
    return value if isinstance(value, str) else to_plain_value(value)


def print_counts(counts: SyncCounts) -> None:
    print("Node Specs sync completed.")
    print(f"Created: {counts.created}")
    print(f"Updated: {counts.updated}")
    print(f"Deprecated: {counts.deprecated}")
    print(f"Skipped: {counts.skipped}")
    print(f"Warnings: {counts.warning_count}")
    if counts.warnings:
        print("\nWarnings:")
        for warning in counts.warnings:
            print(f"- {warning}")


def sync_node_specs(*, yaml_path: Path, database_key: str, dry_run: bool) -> SyncCounts:
    counts = SyncCounts()
    nodes, _ = load_node_specs(yaml_path, counts.warnings)
    client = NotionClient()
    database_id = client.get_database_id(database_key)
    database = client.retrieve_database(database_id)
    available_properties = database["properties"]

    property_warnings: list[str] = []
    node_id_property = schema_property(
        available_properties,
        "node_id",
        "title",
        PROPERTY_MAPPING["node_id"][2],
        property_warnings,
    )
    if not node_id_property:
        fallback_title = title_property_name(available_properties)
        node_id_property = fallback_title
        property_warnings.append(f"Using title property '{fallback_title}' as node_id fallback.")

    for warning in dict.fromkeys(property_warnings):
        if warning not in counts.warnings:
            counts.warn(warning)

    existing_pages = client.query_database(database_id)
    pages_by_node_id = {
        node_id: page
        for page in existing_pages
        if (node_id := page_node_id(page, node_id_property))
    }
    yaml_ids = {node["node_id"] for node in nodes}

    for node in nodes:
        node_id = node["node_id"]
        item_warnings: list[str] = []
        properties = build_properties(node, available_properties, item_warnings)
        for warning in dict.fromkeys(item_warnings):
            if warning not in counts.warnings:
                counts.warn(warning)

        children = build_page_children(node)
        existing_page = pages_by_node_id.get(node_id)

        try:
            if not existing_page:
                counts.created += 1
                if dry_run:
                    print(f"DRY-RUN create {node_id}")
                else:
                    created_page = client.create_page(
                        database_id,
                        properties,
                        children=children[:APPEND_BATCH_SIZE],
                    )
                    if len(children) > APPEND_BATCH_SIZE:
                        append_blocks_in_batches(
                            client,
                            created_page["id"],
                            children[APPEND_BATCH_SIZE:],
                        )
                continue

            changed = changed_properties(properties, existing_page)
            counts.updated += 1
            if dry_run:
                print(f"DRY-RUN update {node_id}")
                continue

            if changed:
                client.update_page(existing_page["id"], changed)
            replace_page_children_preserving_manual_notes(
                client,
                existing_page["id"],
                children,
                counts.warnings,
            )
        except Exception as exc:
            counts.warn(f"{node_id}: {exc}")
            counts.skipped += 1
            if not existing_page:
                counts.created -= 1
            else:
                counts.updated -= 1

    deprecated_payload = {"select": {"name": "deprecated"}}
    status_property = find_database_property(
        available_properties,
        PROPERTY_MAPPING["status"][2],
        allowed_types={"select"},
    )
    if not status_property:
        counts.warn("Missing Notion property 'status'; deprecated handling skipped.")
    else:
        for node_id, page in pages_by_node_id.items():
            if node_id in yaml_ids:
                continue

            try:
                status = page.get("properties", {}).get(status_property, {})
                if property_values_equal(deprecated_payload, status):
                    counts.skipped += 1
                    continue

                counts.deprecated += 1
                if dry_run:
                    print(f"DRY-RUN deprecate {node_id}")
                else:
                    client.update_page(page["id"], {status_property: deprecated_payload})
            except Exception as exc:
                counts.warn(f"{node_id}: failed to deprecate: {exc}")
                counts.skipped += 1

    unkeyed_pages = len(existing_pages) - len(pages_by_node_id)
    if unkeyed_pages:
        counts.skipped += unkeyed_pages
        counts.warn(f"Skipped {unkeyed_pages} Notion page(s) without node_id.")

    return counts


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Sync node_specs.yaml into Notion Node Specs DB.")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print planned operations without writing to Notion.",
    )
    parser.add_argument(
        "--yaml-path",
        default=DEFAULT_YAML_PATH,
        help="YAML file path. Default: core/node_specs.yaml",
    )
    parser.add_argument(
        "--database-key",
        default=DEFAULT_DATABASE_KEY,
        help="database_ids.json key. Default: node_specs",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    yaml_path = resolve_yaml_path(args.yaml_path)

    try:
        counts = sync_node_specs(
            yaml_path=yaml_path,
            database_key=args.database_key,
            dry_run=args.dry_run,
        )
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    print_counts(counts)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
