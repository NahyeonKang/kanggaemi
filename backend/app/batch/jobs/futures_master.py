from __future__ import annotations

import logging
import os
import subprocess
import sys
from pathlib import Path

from app.batch.retry import run_targets
from app.batch.types import JobContext, JobResult, TargetResult


logger = logging.getLogger(__name__)
BACKEND_DIR = Path(__file__).resolve().parents[3]


def run_futures_master_refresh(context: JobContext) -> JobResult:
    if context.since is not None or context.date is not None:
        raise ValueError("futures-master-refresh does not support --since or --date")
    target_configs = context.config["targets"]
    targets = context.targets or list(target_configs)
    unknown = sorted(set(targets) - set(target_configs))
    if unknown:
        raise ValueError(f"unknown futures master targets: {unknown}")

    if context.dry_run:
        return JobResult(
            job_name=context.job_name,
            targets=[
                TargetResult(
                    target=target, success=True, attempts=0,
                    output={"dry_run": True, "command": _command(target_configs[target])},
                )
                for target in targets
            ],
        )

    def load(target: str) -> dict:
        command = _command(target_configs[target])
        env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
        result = subprocess.run(
            command,
            cwd=BACKEND_DIR,
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"master loader failed rc={result.returncode}: "
                f"{(result.stderr or result.stdout).strip()[-2000:]}"
            )
        logger.info(
            "master_loader_succeeded",
            extra={"event": "master_loader_succeeded", "target": target},
        )
        return {"returncode": result.returncode, "command": command}

    return JobResult(
        job_name=context.job_name,
        targets=run_targets(context.job_name, targets, load, context.retry_policy),
    )


def _command(config: dict) -> list[str]:
    args = [sys.executable, "-m", str(config["module"])]
    args.extend(str(value) for value in config.get("args", []))
    return args

