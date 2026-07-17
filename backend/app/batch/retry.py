from __future__ import annotations

import logging
import random
import time
from collections.abc import Callable, Iterable
from typing import TypeVar

from app.batch.types import RetryPolicy, SkipTarget, TargetResult


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
        except SkipTarget as exc:
            logger.warning(
                "target_skipped",
                extra={
                    "event": "target_skipped", "job": job_name, "target": target,
                    "attempt": attempt, "skip_reason": exc.reason, **exc.details,
                },
            )
            return TargetResult(
                target=target, success=True, attempts=attempt,
                output=exc.details, skipped=True, skip_reason=exc.reason,
            )
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
            jitter_factor = 1.0 - policy.jitter_fraction * (1.0 - jitter())
            sleep(min(delay, policy.max_delay_seconds) * jitter_factor)
            delay = min(delay * policy.multiplier, policy.max_delay_seconds)
    raise AssertionError("unreachable")


def run_targets(
    job_name: str,
    targets: Iterable[str],
    operation: Callable[[str], T],
    policy: RetryPolicy,
) -> list[TargetResult]:
    return [run_target(job_name, target, lambda target=target: operation(target), policy) for target in targets]
