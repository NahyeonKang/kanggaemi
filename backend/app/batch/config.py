from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from app.batch.types import RetryPolicy


DEFAULT_CONFIG_PATH = Path(__file__).with_name("jobs.yaml")


def load_batch_config(path: str | Path | None = None) -> dict[str, Any]:
    config_path = Path(path) if path else DEFAULT_CONFIG_PATH
    with config_path.open(encoding="utf-8") as file:
        config = yaml.safe_load(file)
    if not isinstance(config, dict) or not isinstance(config.get("jobs"), dict):
        raise ValueError(f"batch config must contain a jobs mapping: {config_path}")
    return config


def retry_policy(config: dict[str, Any], job_config: dict[str, Any]) -> RetryPolicy:
    values = {**config.get("defaults", {}).get("retry", {}), **job_config.get("retry", {})}
    return RetryPolicy(
        max_attempts=int(values.get("max_attempts", 3)),
        initial_delay_seconds=float(values.get("initial_delay_seconds", 1)),
        multiplier=float(values.get("multiplier", 2)),
        max_delay_seconds=float(values.get("max_delay_seconds", 30)),
    )

