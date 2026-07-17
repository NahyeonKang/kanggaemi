from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass(frozen=True)
class RetryPolicy:
    max_attempts: int = 3
    initial_delay_seconds: float = 1.0
    multiplier: float = 2.0
    max_delay_seconds: float = 30.0
    jitter_fraction: float = 0.5


@dataclass
class TargetResult:
    target: str
    success: bool
    attempts: int
    output: Any = None
    error: str | None = None
    skipped: bool = False
    skip_reason: str | None = None


class SkipTarget(Exception):
    """Marks a known, non-retryable target exclusion without failing the job."""

    def __init__(
        self, reason: str, *, details: dict[str, Any] | None = None
    ) -> None:
        super().__init__(reason)
        self.reason = reason
        self.details = details or {}


@dataclass
class JobResult:
    job_name: str
    targets: list[TargetResult] = field(default_factory=list)

    @property
    def success(self) -> bool:
        return bool(self.targets) and all(item.success for item in self.targets)

    @property
    def succeeded(self) -> int:
        return sum(item.success and not item.skipped for item in self.targets)

    @property
    def skipped(self) -> int:
        return sum(item.skipped for item in self.targets)

    @property
    def failed(self) -> int:
        return sum(not item.success for item in self.targets)


@dataclass(frozen=True)
class JobContext:
    job_name: str
    config: dict[str, Any]
    batch_config: dict[str, Any]
    targets: list[str] | None
    since: str | None
    date: str | None
    dry_run: bool
    retry_policy: RetryPolicy


class JobHandler(Protocol):
    def __call__(self, context: JobContext) -> JobResult: ...
