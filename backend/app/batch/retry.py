from __future__ import annotations

import logging
import random
import time
from collections.abc import Callable, Iterable
from typing import TypeVar

from app.batch.types import RetryPolicy, TargetResult


T = TypeVar("T")
logger = logging.getLogger(__name__)


def run_target(
    job_name: str,
    target: str,
    operation: Callable[[], T],
    policy: RetryPolicy,
    *,
    sleep: Callable[[float], None] = time.sleep,
    jitter: Callable[[], float] = random.random,
) -> TargetResult:
    delay = policy.initial_delay_seconds
    for attempt in range(1, policy.max_attempts + 1):
        try:
            logger.info(
                "target_started",
                extra={"event": "target_started", "job": job_name, "target": target, "attempt": attempt},
            )
            output = operation()
            logger.info(
                "target_succeeded",
                extra={"event": "target_succeeded", "job": job_name, "target": target, "attempt": attempt},
            )
            return TargetResult(target=target, success=True, attempts=attempt, output=output)
        except Exception as exc:  # target isolation is intentional at this boundary
            logger.exception(
                "target_failed",
                extra={
                    "event": "target_failed", "job": job_name, "target": target,
                    "attempt": attempt, "retrying": attempt < policy.max_attempts,
                },
            )
            if attempt == policy.max_attempts:
                return TargetResult(
                    target=target, success=False, attempts=attempt,
                    error=f"{type(exc).__name__}: {exc}",
                )
            sleep(min(delay, policy.max_delay_seconds) * (0.5 + jitter() * 0.5))
            delay = min(delay * policy.multiplier, policy.max_delay_seconds)
    raise AssertionError("unreachable")


def run_targets(
    job_name: str,
    targets: Iterable[str],
    operation: Callable[[str], T],
    policy: RetryPolicy,
) -> list[TargetResult]:
    return [run_target(job_name, target, lambda target=target: operation(target), policy) for target in targets]

