from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


CORE_DIR = Path(__file__).resolve().parents[1] / "core"


def load_yaml(name: str) -> dict[str, Any]:
    with (CORE_DIR / name).open(encoding="utf-8") as file:
        value = yaml.safe_load(file)
    if not isinstance(value, dict):
        raise ValueError(f"invalid core contract: {name}")
    return value


def class_policy(asset_class: str) -> dict[str, Any]:
    for item in load_yaml("asset_class_taxonomy.yaml")["classes"]:
        if item["asset_class"] == asset_class and item.get("status") == "active":
            return item
    raise ValueError(f"unknown active asset_class: {asset_class}")
