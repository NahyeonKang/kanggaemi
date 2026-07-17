from __future__ import annotations

import argparse
import copy
import re
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


# asset_class_taxonomy.yaml defines the controlled vocabulary for asset_class.
# It describes class-level rules: applicable dimensions, default analysis horizon,
# code policy, region/market, and coverage. LLMs should not invent these values.
# asset_taxonomy.yaml is different: it caches individual resolved assets such as
# Samsung Electronics, KOSPI, or USDKRW, and each item references one asset_class.
# factor_catalog.yaml should also reference these asset_class
# values as a controlled vocabulary.

ROOT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_YAML_PATH = "core/asset_class_taxonomy.yaml"
DEFAULT_DATABASE_KEY = "asset_class_taxonomy"
CODE_CHUNK_SIZE = 1800
APPEND_BATCH_SIZE = 80
MANUAL_NOTES_HEADING = "Manual Notes"
SNAKE_CASE_RE = re.compile(r"^[a-z][a-z0-9_]*$")

# default_horizon is a controlled enum (ordered from shortest to longest).
# Values are NOT snake_case (e.g. "1D", "Long-term"), so they are validated
# against this whitelist rather than SNAKE_CASE_RE.
HORIZON_VALUES = ["1D", "1W", "1M", "3M", "6M", "1Y", "Long-term"]
ALLOWED_HORIZONS = set(HORIZON_VALUES)

PROPERTY_MAPPING: dict[str, tuple[str, str, list[str]]] = {
    "asset_class": ("asset_class", "title", ["asset_class", "asset class", "assetclass"]),
    "description": ("description", "rich_text", ["description"]),
    "region": ("region", "select", ["region"]),
    "markets": ("markets", "multi_select", ["markets"]),
    "entity_code_format": ("entity_code_format", "rich_text", ["entity_code_format", "entity code format", "entitycodeformat"]),
    "entity_code_source": ("entity_code_source", "rich_text", ["entity_code_source", "entity code source", "entitycodesource"]),
    "applicable_dimensions": ("applicable_dimensions", "multi_select", ["applicable_dimensions", "applicable dimensions", "applicabledimensions"]),
    "default_horizon": ("default_horizon", "select", ["default_horizon", "default horizon", "defaulthorizon"]),
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

    if not path.is_absolute() and len(path.parts) >= 2 and path.parts[0] in {"core", "configs"}:
        candidates.append(ROOT_DIR / "backend" / "app" / "core" / path.name)

    for candidate in candidates:
        if candidate.exists():
            return candidate

    return candidates[0]


def sibling_core_path(name: str) -> Path:
    return ROOT_DIR / "backend" / "app" / "core" / name


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


def load_yaml_file(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as file:
        return yaml.safe_load(file)


def load_asset_class_taxonomy(path: Path, warnings: list[str]) -> list[dict[str, Any]]:
    try:
        data = load_yaml_file(path)
    except yaml.YAMLError as exc:
        raise ValueError(f"Failed to parse YAML {path}: {exc}") from exc

    classes = data.get("classes") if isinstance(data, dict) else None
    if not isinstance(classes, list):
        raise ValueError(f"{path} must contain a top-level 'classes' list.")

    seen: set[str] = set()
    for index, item in enumerate(classes, start=1):
        asset_class = item.get("asset_class") if isinstance(item, dict) else None
        if not asset_class:
            raise ValueError(f"classes[{index}] must include asset_class.")
        if asset_class in seen:
            raise ValueError(f"Duplicate asset_class in YAML: {asset_class}")
        seen.add(asset_class)

        for field_name in ("asset_class", "region", "status"):
            value = item.get(field_name)
            if isinstance(value, str) and not SNAKE_CASE_RE.match(value):
                warnings.append(
                    f"{asset_class}: '{field_name}' should preferably be lowercase snake_case."
                )

        # default_horizon must be one of the controlled enum values.
        # Invalid value is a hard error; missing value is a soft warning.
        horizon = item.get("default_horizon")
        if horizon is None:
            warnings.append(
                f"{asset_class}: 'default_horizon' is missing; expected one of {HORIZON_VALUES}."
            )
        elif horizon not in ALLOWED_HORIZONS:
            raise ValueError(
                f"{asset_class}: invalid default_horizon '{horizon}'. "
                f"Must be one of {HORIZON_VALUES}."
            )

        item.setdefault("markets", [])
        item.setdefault("applicable_dimensions", [])
        item.setdefault("caveats", [])

    return classes


def optional_yaml(path: Path, warnings: list[str]) -> Any:
    if not path.exists():
        return None
    try:
        return load_yaml_file(path)
    except Exception as exc:
        warnings.append(f"Could not parse optional validation file {path.name}: {exc}")
        return None


def validate_cross_file_consistency(classes: list[dict[str, Any]], warnings: list[str]) -> None:
    taxonomy_asset_classes = {item["asset_class"] for item in classes}

    asset_taxonomy = optional_yaml(sibling_core_path("asset_taxonomy.yaml"), warnings)
    factor_catalog = optional_yaml(sibling_core_path("factor_catalog.yaml"), warnings)

    assets = asset_taxonomy.get("assets") if isinstance(asset_taxonomy, dict) else []
    if isinstance(assets, list):
        for asset in assets:
            if not isinstance(asset, dict):
                continue
            asset_class = asset.get("asset_class")
            if asset_class and asset_class not in taxonomy_asset_classes:
                warnings.append(
                    f"asset_taxonomy asset '{asset.get('asset_code', '<unknown>')}' references unknown asset_class '{asset_class}'."
                )

    factors = factor_catalog.get("factors") if isinstance(factor_catalog, dict) else []
    if isinstance(factors, list):
        for factor in factors:
            if not isinstance(factor, dict):
                continue
            for asset_class in as_list(factor.get("asset_classes", [])):
                if asset_class and asset_class not in taxonomy_asset_classes:
                    warnings.append(
                        f"factor_catalog '{factor.get('factor_id', '<unknown>')}' references unknown asset_class '{asset_class}'."
                    )


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
    asset_class_item: dict[str, Any],
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

        value = get_nested(asset_class_item, source_path, "")
        if expected_type == "multi_select":
            value = as_list(value)
        elif value is None:
            value = ""

        payload = property_payload(expected_type, value)
        if payload is not None:
            properties[property_name] = payload

    title_property = title_property_name(available_properties)
    if title_property not in properties:
        properties[title_property] = title(asset_class_item["asset_class"])

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


def append_text_section(children: list[dict[str, Any]], heading: str, value: Any) -> None:
    if value in (None, "", [], {}):
        return
    children.append(heading_2(heading))
    children.append(paragraph(to_plain_value(value)))


def append_list_section(children: list[dict[str, Any]], heading: str, values: Any) -> None:
    items = as_list(values)
    if not items:
        return
    children.append(heading_2(heading))
    for item in items:
        children.append(bullet_item(item))


def append_yaml_section(children: list[dict[str, Any]], heading: str, value: Any) -> None:
    if value in (None, "", [], {}):
        return
    children.append(heading_2(heading))
    children.extend(yaml_code_blocks(value))


def entity_code_policy(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "entity_code_format": item.get("entity_code_format", ""),
        "entity_code_source": item.get("entity_code_source", ""),
    }


def build_page_children(asset_class_item: dict[str, Any]) -> list[dict[str, Any]]:
    children: list[dict[str, Any]] = []

    append_text_section(children, "Description", asset_class_item.get("description", ""))
    append_text_section(children, "Region", asset_class_item.get("region", ""))
    append_text_section(children, "Default Horizon", asset_class_item.get("default_horizon", ""))
    append_list_section(children, "Markets", asset_class_item.get("markets", []))
    append_yaml_section(children, "Entity Code Policy", entity_code_policy(asset_class_item))
    append_list_section(children, "Applicable Dimensions", asset_class_item.get("applicable_dimensions", []))
    append_list_section(children, "Caveats", asset_class_item.get("caveats", []))
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


def page_asset_class(page: dict[str, Any], asset_class_property: str) -> str:
    page_property = page.get("properties", {}).get(asset_class_property)
    if not page_property:
        return ""

    value = extract_property_value(page_property)
    return value if isinstance(value, str) else to_plain_value(value)


def print_counts(counts: SyncCounts) -> None:
    print("Asset Class Taxonomy sync completed.")
    print(f"Created: {counts.created}")
    print(f"Updated: {counts.updated}")
    print(f"Deprecated: {counts.deprecated}")
    print(f"Skipped: {counts.skipped}")
    print(f"Warnings: {counts.warning_count}")
    if counts.warnings:
        print("\nWarnings:")
        for warning in counts.warnings:
            print(f"- {warning}")


def sync_asset_class_taxonomy(*, yaml_path: Path, database_key: str, dry_run: bool) -> SyncCounts:
    counts = SyncCounts()
    classes = load_asset_class_taxonomy(yaml_path, counts.warnings)
    validate_cross_file_consistency(classes, counts.warnings)

    client = NotionClient()
    database_id = client.get_database_id(database_key)
    database = client.retrieve_database(database_id)
    available_properties = database["properties"]

    property_warnings: list[str] = []
    asset_class_property = schema_property(
        available_properties,
        "asset_class",
        "title",
        PROPERTY_MAPPING["asset_class"][2],
        property_warnings,
    )
    if not asset_class_property:
        fallback_title = title_property_name(available_properties)
        asset_class_property = fallback_title
        property_warnings.append(
            f"Using title property '{fallback_title}' as asset_class fallback."
        )

    for warning in dict.fromkeys(property_warnings):
        if warning not in counts.warnings:
            counts.warn(warning)

    existing_pages = client.query_database(database_id)
    pages_by_asset_class = {
        asset_class: page
        for page in existing_pages
        if (asset_class := page_asset_class(page, asset_class_property))
    }
    yaml_asset_classes = {item["asset_class"] for item in classes}

    for item in classes:
        asset_class = item["asset_class"]
        item_warnings: list[str] = []
        properties = build_properties(item, available_properties, item_warnings)
        for warning in dict.fromkeys(item_warnings):
            if warning not in counts.warnings:
                counts.warn(warning)

        children = build_page_children(item)
        existing_page = pages_by_asset_class.get(asset_class)

        try:
            if not existing_page:
                counts.created += 1
                if dry_run:
                    print(f"DRY-RUN create {asset_class}")
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
                print(f"DRY-RUN update {asset_class}")
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
            counts.warn(f"{asset_class}: {exc}")
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
        for asset_class, page in pages_by_asset_class.items():
            if asset_class in yaml_asset_classes:
                continue

            try:
                status = page.get("properties", {}).get(status_property, {})
                if property_values_equal(deprecated_payload, status):
                    counts.skipped += 1
                    continue

                counts.deprecated += 1
                if dry_run:
                    print(f"DRY-RUN deprecate {asset_class}")
                else:
                    client.update_page(page["id"], {status_property: deprecated_payload})
            except Exception as exc:
                counts.warn(f"{asset_class}: failed to deprecate: {exc}")
                counts.skipped += 1

    unkeyed_pages = len(existing_pages) - len(pages_by_asset_class)
    if unkeyed_pages:
        counts.skipped += unkeyed_pages
        counts.warn(f"Skipped {unkeyed_pages} Notion page(s) without asset_class.")

    return counts


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Sync asset_class_taxonomy.yaml into Notion Asset Class Taxonomy DB."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print planned operations without writing to Notion.",
    )
    parser.add_argument(
        "--yaml-path",
        default=DEFAULT_YAML_PATH,
        help="YAML file path. Default: core/asset_class_taxonomy.yaml",
    )
    parser.add_argument(
        "--database-key",
        default=DEFAULT_DATABASE_KEY,
        help="database_ids.json key. Default: asset_class_taxonomy",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    yaml_path = resolve_yaml_path(args.yaml_path)

    try:
        counts = sync_asset_class_taxonomy(
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