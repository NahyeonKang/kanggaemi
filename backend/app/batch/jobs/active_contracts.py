from __future__ import annotations

from app.batch.dates import normalize_yyyy_mm_dd
from app.batch.resolvers.domestic import resolve_domestic_contract
from app.batch.resolvers.overseas import resolve_overseas_contract
from app.batch.retry import run_targets
from app.batch.types import JobContext, JobResult, TargetResult
from app.db.session import SessionLocal


def run_active_contract_refresh(context: JobContext) -> JobResult:
    if context.since is not None:
        raise ValueError("active-contract-refresh does not support --since")
    as_of_date = normalize_yyyy_mm_dd(context.date)
    configured = _target_configs(context.config)
    targets = context.targets or list(configured)
    unknown = sorted(set(targets) - set(configured))
    if unknown:
        raise ValueError(f"unknown active-contract targets: {unknown}")

    if context.dry_run:
        return JobResult(
            job_name=context.job_name,
            targets=[
                TargetResult(
                    target=target, success=True, attempts=0,
                    output={"dry_run": True, "as_of_date": as_of_date, **configured[target]},
                )
                for target in targets
            ],
        )

    def resolve(target: str) -> dict:
        values = configured[target]
        with SessionLocal() as db:
            if values["market"] == "overseas":
                return resolve_overseas_contract(
                    db,
                    as_of_date=as_of_date,
                    product=values["product"],
                    product_code=values["product_code"],
                )
            return resolve_domestic_contract(
                db,
                as_of_date=as_of_date,
                product=values["product"],
                underlying_cd=values["underlying_cd"],
                market_type=values["market_type"],
                candidate_count=int(values["candidate_count"]),
                lookback_days=int(values["lookback_days"]),
                rollover_business_days=int(values["rollover_business_days"]),
            )

    return JobResult(
        job_name=context.job_name,
        targets=run_targets(context.job_name, targets, resolve, context.retry_policy),
    )


def _target_configs(config: dict) -> dict[str, dict]:
    targets: dict[str, dict] = {}
    for product, values in config["overseas"].items():
        targets[f"overseas:{product}"] = {
            "market": "overseas", "product": product, **values,
        }
    for product, values in config["domestic"].items():
        targets[f"domestic:{product}"] = {
            "market": "domestic", "product": product, **values,
        }
    return targets
