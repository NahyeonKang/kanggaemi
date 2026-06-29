from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

if __package__:
    from .client import (
        NotionClient,
        changed_properties,
        extract_property_value,
        find_database_property,
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
        extract_property_value,
        find_database_property,
        property_payload,
        property_values_equal,
        title,
        title_property_name,
        to_plain_value,
    )


ROOT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_CATALOG_PATH = ROOT_DIR / "backend" / "app" / "core" / "factor_catalog.yaml"
DATABASE_KEY = "factor_catalog"

PROPERTY_ALIASES = {
    "factor_id": ["factor_id", "factor id", "factorid", "id"],
    "factor_name": ["factor_name", "factor name", "factorname", "name"],
    "asset_classes": ["asset_classes", "asset classes", "assetclasses"],
    "data_spec_id": ["data_spec_id", "data spec id", "dataspecid"],
    "cumulative_type": ["cumulative_type", "cumulative type", "cumulativetype"],
}


@dataclass
class SyncCounts:
    created: int = 0
    updated: int = 0
    deprecated: int = 0
    skipped: int = 0


def aliases_for(key: str) -> list[str]:
    return PROPERTY_ALIASES.get(key, [key])


def load_catalog(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as file:
        data = yaml.safe_load(file)

    factors = data.get("factors") if isinstance(data, dict) else None
    if not isinstance(factors, list):
        raise ValueError(f"{path} must contain a top-level 'factors' list.")

    seen: set[str] = set()
    for factor in factors:
        factor_id = factor.get("factor_id") if isinstance(factor, dict) else None
        if not factor_id:
            raise ValueError("Every factor must include factor_id.")
        if factor_id in seen:
            raise ValueError(f"Duplicate factor_id in YAML: {factor_id}")
        seen.add(factor_id)

    return factors


def build_factor_properties(
    factor: dict[str, Any],
    schema: dict[str, Any],
    *,
    factor_id_property: str,
    title_property: str,
) -> dict[str, Any]:
    properties: dict[str, Any] = {}

    for key, value in factor.items():
        property_name = find_database_property(schema, aliases_for(key))
        if not property_name:
            continue

        payload = property_payload(schema[property_name]["type"], value)
        if payload is not None:
            properties[property_name] = payload

    if factor_id_property not in properties:
        payload = property_payload(schema[factor_id_property]["type"], factor["factor_id"])
        if payload is not None:
            properties[factor_id_property] = payload

    if title_property not in properties:
        title_value = factor.get("factor_name") or factor["factor_id"]
        properties[title_property] = title(title_value)

    return properties


def page_factor_id(page: dict[str, Any], factor_id_property: str) -> str:
    page_property = page.get("properties", {}).get(factor_id_property)
    if not page_property:
        return ""

    value = extract_property_value(page_property)
    return value if isinstance(value, str) else to_plain_value(value)


def print_counts(counts: SyncCounts) -> None:
    print(f"created={counts.created}")
    print(f"updated={counts.updated}")
    print(f"deprecated={counts.deprecated}")
    print(f"skipped={counts.skipped}")


def sync_factor_catalog(*, catalog_path: Path, dry_run: bool) -> SyncCounts:
    factors = load_catalog(catalog_path)
    client = NotionClient()
    database_id = client.get_database_id(DATABASE_KEY)
    database = client.retrieve_database(database_id)
    schema = database["properties"]

    factor_id_property = find_database_property(
        schema,
        aliases_for("factor_id"),
        allowed_types={"title", "rich_text"},
    )
    if not factor_id_property:
        raise RuntimeError(
            "Notion database must have a factor_id property with title or rich_text type."
        )

    status_property = find_database_property(schema, "status", allowed_types={"select"})
    if not status_property:
        raise RuntimeError("Notion database must have a status select property.")

    title_property = title_property_name(schema)
    existing_pages = client.query_database(database_id)
    pages_by_factor_id = {
        factor_id: page
        for page in existing_pages
        if (factor_id := page_factor_id(page, factor_id_property))
    }

    counts = SyncCounts()
    yaml_factor_ids = {factor["factor_id"] for factor in factors}

    for factor in factors:
        factor_id = factor["factor_id"]
        desired = build_factor_properties(
            factor,
            schema,
            factor_id_property=factor_id_property,
            title_property=title_property,
        )
        existing_page = pages_by_factor_id.get(factor_id)

        if not existing_page:
            counts.created += 1
            if not dry_run:
                client.create_page(database_id, desired)
            continue

        changed = changed_properties(desired, existing_page)
        if changed:
            counts.updated += 1
            if not dry_run:
                client.update_page(existing_page["id"], changed)
        else:
            counts.skipped += 1

    deprecated_payload = {"select": {"name": "deprecated"}}
    for factor_id, page in pages_by_factor_id.items():
        if factor_id in yaml_factor_ids:
            continue

        status = page.get("properties", {}).get(status_property, {})
        if property_values_equal(deprecated_payload, status):
            counts.skipped += 1
            continue

        counts.deprecated += 1
        if not dry_run:
            client.update_page(page["id"], {status_property: deprecated_payload})

    unkeyed_pages = len(existing_pages) - len(pages_by_factor_id)
    counts.skipped += unkeyed_pages
    if unkeyed_pages:
        print(
            f"warning: skipped {unkeyed_pages} Notion page(s) without factor_id",
            file=sys.stderr,
        )

    return counts


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Upsert backend/app/core/factor_catalog.yaml into Notion."
    )
    parser.add_argument(
        "--catalog",
        type=Path,
        default=DEFAULT_CATALOG_PATH,
        help=f"YAML catalog path. Default: {DEFAULT_CATALOG_PATH}",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print counts without creating or updating Notion pages.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    try:
        counts = sync_factor_catalog(catalog_path=args.catalog, dry_run=args.dry_run)
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    print_counts(counts)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
