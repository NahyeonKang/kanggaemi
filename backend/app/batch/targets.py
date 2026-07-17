from __future__ import annotations

from app.batch.types import JobContext
from app.db.session import SessionLocal
from app.repositories.universe_membership_repository import UniverseMembershipRepository


def latest_universe_tickers(context: JobContext) -> list[str]:
    universe_job_name = str(context.config["universe_job"])
    universe_config = context.batch_config["jobs"][universe_job_name]
    expected_counts = {
        market: int(values["top_n"])
        for market, values in universe_config["markets"].items()
    }
    with SessionLocal() as db:
        return UniverseMembershipRepository().get_latest_tickers(db, expected_counts)


def selected_configured_targets(
    context: JobContext, configured: dict[str, dict]
) -> list[str]:
    targets = list(dict.fromkeys(context.targets or list(configured)))
    unknown = sorted(set(targets) - set(configured))
    if unknown:
        raise ValueError(f"unknown {context.job_name} targets: {unknown}")
    if not targets:
        raise RuntimeError(f"no targets configured for {context.job_name}")
    return targets
