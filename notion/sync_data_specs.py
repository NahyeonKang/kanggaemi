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
        title,
        title_property_name,
        to_plain_value,
    )


ROOT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_YAML_PATH = "core/data_specs.yaml"
DEFAULT_DATABASE_KEY = "data_specs"
CODE_CHUNK_SIZE = 1800
APPEND_BATCH_SIZE = 80
MANUAL_NOTES_HEADING = "Manual Notes"

PROPERTY_MAPPING: dict[str, tuple[str, str, list[str]]] = {
    "data_spec_id": ("data_spec_id", "title", ["data_spec_id", "data spec id", "dataspecid"]),
    "name": ("name", "rich_text", ["name"]),
    "provider": ("source.provider", "select", ["provider"]),
    "asset_classes": ("coverage.asset_classes", "multi_select", ["asset_classes", "asset classes", "assetclasses"]),
    "markets": ("coverage.markets", "multi_select", ["markets"]),
    "regions": ("coverage.regions", "multi_select", ["regions"]),
    "dimensions": ("usage.dimensions", "multi_select", ["dimensions"]),
    "related_factors": ("usage.related_factors", "multi_select", ["related_factors", "related factors", "relatedfactors"]),
    "frequency": ("data_contract.frequency", "select", ["frequency"]),
    "cumulative_type": ("data_contract.cumulative_type", "select", ["cumulative_type", "cumulative type", "cumulativetype"]),
    "update_timing": ("data_contract.update_timing", "rich_text", ["update_timing", "update timing", "updatetiming"]),
    "expected_lag": ("data_contract.expected_lag", "rich_text", ["expected_lag", "expected lag", "expectedlag"]),
    "status": ("status", "select", ["status"]),
}

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


def yaml_dump(value: Any) -> str:
    if value in (None, [], {}):
        return ""
    return yaml.safe_dump(value, allow_unicode=True, sort_keys=False).strip()


def as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def load_data_specs(path: Path) -> list[dict[str, Any]]:
    try:
        with path.open("r", encoding="utf-8") as file:
            data = yaml.safe_load(file)
    except yaml.YAMLError as exc:
        raise ValueError(f"Failed to parse YAML {path}: {exc}") from exc

    specs = data.get("data_specs") if isinstance(data, dict) else None
    if not isinstance(specs, list):
        raise ValueError(f"{path} must contain a top-level 'data_specs' list.")

    seen: set[str] = set()
    for index, spec in enumerate(specs, start=1):
        data_spec_id = spec.get("data_spec_id") if isinstance(spec, dict) else None
        if not data_spec_id:
            raise ValueError(f"data_specs[{index}] must include data_spec_id.")
        if data_spec_id in seen:
            raise ValueError(f"Duplicate data_spec_id in YAML: {data_spec_id}")
        seen.add(data_spec_id)

    return specs


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
    spec: dict[str, Any],
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

        value = get_nested(spec, source_path, "")
        if expected_type == "multi_select":
            value = as_list(value)
        elif value is None:
            value = ""

        payload = property_payload(expected_type, value)
        if payload is not None:
            properties[property_name] = payload

    title_property = title_property_name(available_properties)
    if title_property not in properties:
        properties[title_property] = title(spec["data_spec_id"])

    return properties


def text_block_lines(value: Any) -> str:
    if value in (None, [], {}):
        return ""
    if isinstance(value, list):
        return "\n".join(f"- {to_plain_value(item)}" for item in value)
    if isinstance(value, dict):
        return yaml_dump(value)
    return to_plain_value(value)


def append_text_section(children: list[dict[str, Any]], heading: str, value: Any) -> None:
    children.append(heading_2(heading))
    text = text_block_lines(value)
    children.append(paragraph(text or ""))


def append_yaml_section(children: list[dict[str, Any]], heading: str, value: Any) -> None:
    children.append(heading_2(heading))
    dumped = yaml_dump(value)
    if not dumped:
        children.append(paragraph(""))
        return

    for index in range(0, len(dumped), CODE_CHUNK_SIZE):
        children.append(code_block(dumped[index : index + CODE_CHUNK_SIZE], "yaml"))


def build_page_children(spec: dict[str, Any]) -> list[dict[str, Any]]:
    children: list[dict[str, Any]] = []

    append_text_section(children, "Description", spec.get("description", ""))
    append_yaml_section(children, "Source", spec.get("source", {}))
    append_yaml_section(children, "Coverage", spec.get("coverage", {}))
    append_yaml_section(children, "Usage", spec.get("usage", {}))
    append_yaml_section(children, "Params", spec.get("params", {}))
    append_yaml_section(children, "Data Contract", spec.get("data_contract", {}))
    append_yaml_section(children, "Output Schema", spec.get("output_schema", {}))
    append_yaml_section(children, "Validation", spec.get("validation", {}))
    append_text_section(children, "Caveats", spec.get("caveats", []))
    append_text_section(children, "Notes", spec.get("notes", []))
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


def page_data_spec_id(page: dict[str, Any], data_spec_id_property: str) -> str:
    page_property = page.get("properties", {}).get(data_spec_id_property)
    if not page_property:
        return ""

    value = extract_property_value(page_property)
    return value if isinstance(value, str) else to_plain_value(value)


def print_counts(counts: SyncCounts) -> None:
    print("DataSpec sync completed.")
    print(f"Created: {counts.created}")
    print(f"Updated: {counts.updated}")
    print(f"Deprecated: {counts.deprecated}")
    print(f"Skipped: {counts.skipped}")
    print(f"Warnings: {counts.warning_count}")
    if counts.warnings:
        print("\nWarnings:")
        for warning in counts.warnings:
            print(f"- {warning}")


def sync_data_specs(*, yaml_path: Path, database_key: str, dry_run: bool) -> SyncCounts:
    specs = load_data_specs(yaml_path)
    client = NotionClient()
    database_id = client.get_database_id(database_key)
    database = client.retrieve_database(database_id)
    available_properties = database["properties"]
    counts = SyncCounts()

    property_warnings: list[str] = []
    data_spec_id_property = schema_property(
        available_properties,
        "data_spec_id",
        "title",
        PROPERTY_MAPPING["data_spec_id"][2],
        property_warnings,
    )
    if not data_spec_id_property:
        fallback_title = title_property_name(available_properties)
        data_spec_id_property = fallback_title
        property_warnings.append(
            f"Using title property '{fallback_title}' as data_spec_id fallback."
        )

    for warning in dict.fromkeys(property_warnings):
        counts.warn(warning)

    existing_pages = client.query_database(database_id)
    pages_by_data_spec_id = {
        data_spec_id: page
        for page in existing_pages
        if (data_spec_id := page_data_spec_id(page, data_spec_id_property))
    }
    yaml_ids = {spec["data_spec_id"] for spec in specs}

    for spec in specs:
        data_spec_id = spec["data_spec_id"]
        item_warnings: list[str] = []
        properties = build_properties(spec, available_properties, item_warnings)
        for warning in dict.fromkeys(item_warnings):
            if warning not in counts.warnings:
                counts.warn(warning)

        children = build_page_children(spec)
        existing_page = pages_by_data_spec_id.get(data_spec_id)

        try:
            if not existing_page:
                counts.created += 1
                if dry_run:
                    print(f"DRY-RUN create {data_spec_id}")
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
                print(f"DRY-RUN update {data_spec_id}")
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
            counts.warn(f"{data_spec_id}: {exc}")
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
        for data_spec_id, page in pages_by_data_spec_id.items():
            if data_spec_id in yaml_ids:
                continue

            try:
                status = page.get("properties", {}).get(status_property, {})
                if property_values_equal(deprecated_payload, status):
                    counts.skipped += 1
                    continue

                counts.deprecated += 1
                if dry_run:
                    print(f"DRY-RUN deprecate {data_spec_id}")
                else:
                    client.update_page(page["id"], {status_property: deprecated_payload})
            except Exception as exc:
                counts.warn(f"{data_spec_id}: failed to deprecate: {exc}")
                counts.skipped += 1

    unkeyed_pages = len(existing_pages) - len(pages_by_data_spec_id)
    if unkeyed_pages:
        counts.skipped += unkeyed_pages
        counts.warn(f"Skipped {unkeyed_pages} Notion page(s) without data_spec_id.")

    return counts


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Sync data_specs.yaml into Notion DataSpecs DB.")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print planned operations without writing to Notion.",
    )
    parser.add_argument(
        "--yaml-path",
        default=DEFAULT_YAML_PATH,
        help="YAML file path. Default: core/data_specs.yaml",
    )
    parser.add_argument(
        "--database-key",
        default=DEFAULT_DATABASE_KEY,
        help="database_ids.json key. Default: data_specs",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    yaml_path = resolve_yaml_path(args.yaml_path)

    try:
        counts = sync_data_specs(
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
