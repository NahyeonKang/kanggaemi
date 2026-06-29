from __future__ import annotations

import argparse
import copy
import sys
from dataclasses import dataclass, field
from datetime import date, datetime
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


# asset_class_taxonomy.yaml is the authoritative class-level vocabulary. It
# defines valid asset_class values and their policy: applicable dimensions,
# default data specs, code formats, and data coverage.
# asset_taxonomy.yaml is different: it is an instance cache/registry of resolved
# real assets such as Samsung Electronics, KOSPI, or USDKRW. Each asset instance
# must reference asset_class_taxonomy.yaml via asset_class. Dimensions and data
# specs are intentionally read from asset_class_taxonomy.yaml, not duplicated here.

ROOT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_YAML_PATH = "configs/asset_taxonomy.yaml"
DEFAULT_CLASS_TAXONOMY_PATH = "configs/asset_class_taxonomy.yaml"
DEFAULT_DATABASE_KEY = "asset_taxonomy"
CODE_CHUNK_SIZE = 1800
APPEND_BATCH_SIZE = 80
MANUAL_NOTES_HEADING = "Manual Notes"
STALE_VERIFIED_DAYS = 365

PROPERTY_MAPPING: dict[str, tuple[str, str, list[str]]] = {
    "asset_code": ("asset_code", "title", ["asset_code", "asset code", "assetcode"]),
    "asset_name": ("asset_name", "rich_text", ["asset_name", "asset name", "assetname"]),
    "asset_class": ("asset_class", "select", ["asset_class", "asset class", "assetclass"]),
    "region": ("region", "select", ["region"]),
    "market": ("market", "select", ["market"]),
    "sector": ("sector", "rich_text", ["sector"]),
    "aliases": ("aliases", "rich_text", ["aliases", "alias"]),
    "resolved_by": ("resolved_by", "select", ["resolved_by", "resolved by", "resolvedby"]),
    "verified_at": ("verified_at", "date", ["verified_at", "verified at", "verifiedat"]),
    "expires_at": ("expires_at", "date", ["expires_at", "expires at", "expiresat"]),
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


def to_iso_date(value: Any) -> str | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return str(value)


def parse_iso_date(value: Any) -> date | None:
    text = to_iso_date(value)
    if not text:
        return None
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None


def aliases_text(value: Any) -> str:
    return ", ".join(str(item) for item in as_list(value) if item is not None)


def normalize_asset(asset: dict[str, Any], index: int, warnings: list[str]) -> dict[str, Any]:
    raw_asset_code = asset.get("asset_code")
    if raw_asset_code in (None, ""):
        raise ValueError(f"assets[{index}] must include asset_code.")
    if not isinstance(raw_asset_code, str):
        warnings.append(
            f"assets[{index}] asset_code was {type(raw_asset_code).__name__}; converted to string. Quote asset_code in YAML to preserve leading zeroes."
        )

    normalized = dict(asset)
    normalized["asset_code"] = str(raw_asset_code)
    normalized.setdefault("aliases", [])
    normalized.setdefault("sector", None)
    normalized.setdefault("expires_at", None)
    normalized["verified_at"] = to_iso_date(normalized.get("verified_at"))
    normalized["expires_at"] = to_iso_date(normalized.get("expires_at"))
    return normalized


def load_asset_taxonomy(path: Path, warnings: list[str]) -> list[dict[str, Any]]:
    try:
        data = load_yaml_file(path)
    except yaml.YAMLError as exc:
        raise ValueError(f"Failed to parse YAML {path}: {exc}") from exc

    assets = data.get("assets") if isinstance(data, dict) else None
    if not isinstance(assets, list):
        raise ValueError(f"{path} must contain a top-level 'assets' list.")

    normalized_assets: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, asset in enumerate(assets, start=1):
        if not isinstance(asset, dict):
            raise ValueError(f"assets[{index}] must be an object.")

        normalized = normalize_asset(asset, index, warnings)
        asset_code = normalized["asset_code"]
        if asset_code in seen:
            raise ValueError(f"Duplicate asset_code in YAML: {asset_code}")
        seen.add(asset_code)

        for field_name in ("asset_name", "asset_class", "region", "market", "status"):
            if normalized.get(field_name) in (None, ""):
                warnings.append(f"{asset_code}: missing recommended field '{field_name}'.")

        normalized_assets.append(normalized)

    return normalized_assets


def load_class_policy_map(path: Path, warnings: list[str]) -> dict[str, dict[str, Any]]:
    if not path.exists():
        warnings.append(f"asset_class taxonomy file not found: {path}")
        return {}

    try:
        data = load_yaml_file(path)
    except Exception as exc:
        warnings.append(f"Could not parse asset_class taxonomy file {path}: {exc}")
        return {}

    classes = data.get("classes") if isinstance(data, dict) else []
    if not isinstance(classes, list):
        warnings.append(f"asset_class taxonomy file {path} must contain a 'classes' list.")
        return {}

    return {
        item["asset_class"]: item
        for item in classes
        if isinstance(item, dict) and item.get("asset_class")
    }


def validate_asset_consistency(
    assets: list[dict[str, Any]],
    class_policy_by_asset_class: dict[str, dict[str, Any]],
    warnings: list[str],
) -> None:
    today = date.today()
    for asset in assets:
        asset_code = asset["asset_code"]
        asset_class = asset.get("asset_class")
        class_policy = class_policy_by_asset_class.get(asset_class)

        if asset_class and not class_policy:
            warnings.append(f"{asset_code}: unknown asset_class '{asset_class}'.")

        if class_policy:
            class_region = class_policy.get("region")
            asset_region = asset.get("region")
            if class_region and asset_region and class_region != asset_region:
                warnings.append(
                    f"{asset_code}: region '{asset_region}' differs from class policy region '{class_region}'."
                )

            markets = as_list(class_policy.get("markets"))
            asset_market = asset.get("market")
            if markets and asset_market and asset_market not in markets:
                warnings.append(
                    f"{asset_code}: market '{asset_market}' is not listed in class policy markets {markets}."
                )

        expires_at = parse_iso_date(asset.get("expires_at"))
        if expires_at and expires_at < today and asset.get("status") == "active":
            warnings.append(f"{asset_code}: expires_at is in the past but status is active.")

        verified_at = parse_iso_date(asset.get("verified_at"))
        if not verified_at:
            warnings.append(f"{asset_code}: verified_at is missing or invalid.")
        elif (today - verified_at).days > STALE_VERIFIED_DAYS:
            warnings.append(f"{asset_code}: verified_at is older than {STALE_VERIFIED_DAYS} days.")

        if asset_class == "kr_equity" and not (isinstance(asset_code, str) and len(asset_code) == 6 and asset_code.isdigit()):
            warnings.append(f"{asset_code}: kr_equity asset_code should be a 6-digit string.")

        if asset_class in {"kr_equity", "us_equity"} and not asset.get("sector"):
            warnings.append(f"{asset_code}: sector is missing for {asset_class}.")


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
    asset: dict[str, Any],
    available_properties: dict[str, Any],
    today_iso: str,
    warnings: list[str] | None = None,
) -> dict[str, Any]:
    _ = today_iso
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

        value = get_nested(asset, source_path, "")
        if notion_name == "aliases":
            value = aliases_text(value)
        elif expected_type == "date":
            value = to_iso_date(value)
        elif value is None:
            value = ""

        payload = property_payload(expected_type, value)
        if payload is not None:
            properties[property_name] = payload

    title_property = title_property_name(available_properties)
    if title_property not in properties:
        properties[title_property] = title(asset["asset_code"])

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


def append_key_values(children: list[dict[str, Any]], heading: str, values: dict[str, Any]) -> None:
    filtered = {key: value for key, value in values.items() if value not in (None, "", [], {})}
    if not filtered:
        return

    children.append(heading_2(heading))
    for key, value in filtered.items():
        children.append(paragraph(f"{key}: {to_plain_value(value)}"))


def append_list_section(children: list[dict[str, Any]], heading: str, values: Any) -> None:
    items = as_list(values)
    if not items:
        return
    children.append(heading_2(heading))
    for item in items:
        children.append(bullet_item(item))


def class_policy_summary(class_policy: dict[str, Any] | None) -> dict[str, Any]:
    if not class_policy:
        return {}
    return {
        "asset_class": class_policy.get("asset_class"),
        "description": class_policy.get("description"),
        "applicable_dimensions": class_policy.get("applicable_dimensions"),
        "default_data_specs": class_policy.get("default_data_specs"),
        "data_coverage": class_policy.get("data_coverage"),
        "caveats": class_policy.get("caveats"),
    }


def build_page_children(asset: dict[str, Any], class_policy: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    children: list[dict[str, Any]] = []

    append_key_values(
        children,
        "Asset Summary",
        {
            "Asset Code": asset.get("asset_code"),
            "Asset Name": asset.get("asset_name"),
            "Asset Class": asset.get("asset_class"),
            "Region": asset.get("region"),
            "Market": asset.get("market"),
            "Sector": asset.get("sector"),
            "Status": asset.get("status"),
        },
    )
    append_key_values(
        children,
        "Resolution Metadata",
        {
            "Resolved By": asset.get("resolved_by"),
            "Verified At": asset.get("verified_at"),
            "Expires At": asset.get("expires_at"),
        },
    )
    append_list_section(children, "Aliases", asset.get("aliases", []))

    summary = class_policy_summary(class_policy)
    if summary:
        children.append(heading_2("Class Policy Reference"))
        children.extend(yaml_code_blocks(summary))

    children.append(heading_2("Raw YAML"))
    children.extend(yaml_code_blocks(asset))
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


def page_asset_code(page: dict[str, Any], asset_code_property: str) -> str:
    page_property = page.get("properties", {}).get(asset_code_property)
    if not page_property:
        return ""

    value = extract_property_value(page_property)
    return value if isinstance(value, str) else to_plain_value(value)


def print_counts(counts: SyncCounts) -> None:
    print("Asset Taxonomy sync completed.")
    print(f"Created: {counts.created}")
    print(f"Updated: {counts.updated}")
    print(f"Deprecated: {counts.deprecated}")
    print(f"Skipped: {counts.skipped}")
    print(f"Warnings: {counts.warning_count}")
    if counts.warnings:
        print("\nWarnings:")
        for warning in counts.warnings:
            print(f"- {warning}")


def sync_asset_taxonomy(
    *,
    yaml_path: Path,
    class_taxonomy_path: Path,
    database_key: str,
    dry_run: bool,
) -> SyncCounts:
    counts = SyncCounts()
    assets = load_asset_taxonomy(yaml_path, counts.warnings)
    class_policy_by_asset_class = load_class_policy_map(class_taxonomy_path, counts.warnings)
    validate_asset_consistency(assets, class_policy_by_asset_class, counts.warnings)

    client = NotionClient()
    database_id = client.get_database_id(database_key)
    database = client.retrieve_database(database_id)
    available_properties = database["properties"]
    today_iso = date.today().isoformat()

    property_warnings: list[str] = []
    asset_code_property = schema_property(
        available_properties,
        "asset_code",
        "title",
        PROPERTY_MAPPING["asset_code"][2],
        property_warnings,
    )
    if not asset_code_property:
        fallback_title = title_property_name(available_properties)
        asset_code_property = fallback_title
        property_warnings.append(
            f"Using title property '{fallback_title}' as asset_code fallback."
        )

    for warning in dict.fromkeys(property_warnings):
        if warning not in counts.warnings:
            counts.warn(warning)

    existing_pages = client.query_database(database_id)
    pages_by_asset_code = {
        asset_code: page
        for page in existing_pages
        if (asset_code := page_asset_code(page, asset_code_property))
    }
    yaml_asset_codes = {asset["asset_code"] for asset in assets}

    for asset in assets:
        asset_code = asset["asset_code"]
        asset_name = asset.get("asset_name", "")
        item_warnings: list[str] = []
        properties = build_properties(asset, available_properties, today_iso, item_warnings)
        for warning in dict.fromkeys(item_warnings):
            if warning not in counts.warnings:
                counts.warn(warning)

        class_policy = class_policy_by_asset_class.get(asset.get("asset_class"))
        if asset.get("asset_class") and not class_policy:
            if f"{asset_code}: unknown asset_class '{asset.get('asset_class')}'." not in counts.warnings:
                counts.warn(f"{asset_code}: unknown asset_class '{asset.get('asset_class')}'.")
        children = build_page_children(asset, class_policy)
        existing_page = pages_by_asset_code.get(asset_code)

        try:
            if not existing_page:
                counts.created += 1
                if dry_run:
                    print(f"DRY-RUN create {asset_code}")
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
                print(f"DRY-RUN update {asset_code}")
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
            counts.warn(f"{asset_code} ({asset_name}): {exc}")
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
        for asset_code, page in pages_by_asset_code.items():
            if asset_code in yaml_asset_codes:
                continue

            try:
                status = page.get("properties", {}).get(status_property, {})
                if property_values_equal(deprecated_payload, status):
                    counts.skipped += 1
                    continue

                counts.deprecated += 1
                if dry_run:
                    print(f"DRY-RUN deprecate {asset_code}")
                else:
                    client.update_page(page["id"], {status_property: deprecated_payload})
            except Exception as exc:
                counts.warn(f"{asset_code}: failed to deprecate: {exc}")
                counts.skipped += 1

    unkeyed_pages = len(existing_pages) - len(pages_by_asset_code)
    if unkeyed_pages:
        counts.skipped += unkeyed_pages
        counts.warn(f"Skipped {unkeyed_pages} Notion page(s) without asset_code.")

    return counts


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Sync asset_taxonomy.yaml into Notion Asset Taxonomy DB.")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print planned operations without writing to Notion.",
    )
    parser.add_argument(
        "--yaml-path",
        default=DEFAULT_YAML_PATH,
        help="YAML file path. Default: configs/asset_taxonomy.yaml",
    )
    parser.add_argument(
        "--class-taxonomy-path",
        default=DEFAULT_CLASS_TAXONOMY_PATH,
        help="Asset class taxonomy YAML path. Default: configs/asset_class_taxonomy.yaml",
    )
    parser.add_argument(
        "--database-key",
        default=DEFAULT_DATABASE_KEY,
        help="database_ids.json key. Default: asset_taxonomy",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    yaml_path = resolve_yaml_path(args.yaml_path)
    class_taxonomy_path = resolve_yaml_path(args.class_taxonomy_path)

    try:
        counts = sync_asset_taxonomy(
            yaml_path=yaml_path,
            class_taxonomy_path=class_taxonomy_path,
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
