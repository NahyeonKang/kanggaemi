from __future__ import annotations

from sqlalchemy.orm import Session

from app.batch.dates import normalize_yyyy_mm_dd
from app.batch.retry import run_targets
from app.batch.types import JobContext, JobResult, TargetResult
from app.db.session import SessionLocal
from app.repositories.universe_membership_repository import UniverseMembershipRepository
from app.services.market_cap_service import MarketCapService


def run_universe_refresh(context: JobContext) -> JobResult:
    if context.since is not None:
        raise ValueError("universe-refresh does not support --since; use --date for the snapshot date")
    market_configs = context.config.get("markets", {})
    targets = context.targets or list(market_configs)
    unknown = sorted(set(targets) - set(market_configs))
    if unknown:
        raise ValueError(f"unknown universe markets: {unknown}")
    univ_date = normalize_yyyy_mm_dd(context.date)

    if context.dry_run:
        return JobResult(
            job_name=context.job_name,
            targets=[
                TargetResult(
                    target=market, success=True, attempts=0,
                    output={"dry_run": True, "univ_date": univ_date, **market_configs[market]},
                )
                for market in targets
            ],
        )

    service = MarketCapService()
    membership_repo = UniverseMembershipRepository()

    def sync_market(market: str) -> dict:
        top_n = int(market_configs[market]["top_n"])
        with SessionLocal() as db:
            return _sync_market(
                db, service, membership_repo, market, top_n,
                str(context.config["div_cls_code"]), univ_date,
            )

    return JobResult(
        job_name=context.job_name,
        targets=run_targets(context.job_name, targets, sync_market, context.retry_policy),
    )


def _sync_market(
    db: Session,
    service: MarketCapService,
    membership_repo: UniverseMembershipRepository,
    market: str,
    top_n: int,
    div_cls_code: str,
    univ_date: str,
) -> dict:
    sync_result = service.sync_market_cap(
        db, market=market, div_cls_code=div_cls_code, top_n=top_n, date=univ_date
    )
    tickers = service.get_top_tickers(
        db, market=market, top_n=top_n, observation_date=univ_date
    )
    ticker_set = set(tickers)
    ranking = [
        row
        for row in service.get_market_cap(db, market, univ_date, top_n)
        if row.ticker in ticker_set
    ]
    if len(ranking) != top_n:
        raise RuntimeError(f"expected {top_n} {market} members, got {len(ranking)}")
    membership_affected = membership_repo.upsert_market_snapshot(db, univ_date, market, ranking)
    return {
        **sync_result,
        "universe_members": len(ranking),
        "membership_affected": membership_affected,
    }
