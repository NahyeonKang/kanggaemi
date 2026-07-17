from __future__ import annotations

from app.batch.dates import normalize_yyyymmdd
from app.batch.retry import run_targets
from app.batch.types import JobContext, JobResult, TargetResult
from app.db.session import SessionLocal
from app.repositories.universe_membership_repository import UniverseMembershipRepository
from app.services.instrument_price_service import InstrumentPriceService


def run_stock_prices(context: JobContext) -> JobResult:
    universe_job_name = str(context.config["universe_job"])
    universe_config = context.batch_config["jobs"][universe_job_name]
    expected_counts = {
        market: int(values["top_n"])
        for market, values in universe_config["markets"].items()
    }
    targets = context.targets or _latest_tickers(expected_counts)
    targets = list(dict.fromkeys(targets))
    if not targets:
        raise RuntimeError("no stock targets; run universe-refresh first or pass --targets")

    start_date = normalize_yyyymmdd(context.since)
    end_date = normalize_yyyymmdd(context.date)
    if start_date and end_date and start_date > end_date:
        raise ValueError("--since must be on or before --date")

    if context.dry_run:
        return JobResult(
            job_name=context.job_name,
            targets=[
                TargetResult(
                    target=ticker, success=True, attempts=0,
                    output={"dry_run": True, "start_date": start_date, "end_date": end_date},
                )
                for ticker in targets
            ],
        )

    service = InstrumentPriceService()

    def sync_ticker(ticker: str) -> dict:
        with SessionLocal() as db:
            return service.sync_chart(
                db,
                asset_class=str(context.config["asset_class"]),
                entity_code=ticker,
                period=str(context.config.get("period", "D")),
                start_date=start_date,
                end_date=end_date,
                adj=str(context.config.get("adj", "0")),
            )

    return JobResult(
        job_name=context.job_name,
        targets=run_targets(context.job_name, targets, sync_ticker, context.retry_policy),
    )


def _latest_tickers(expected_counts: dict[str, int]) -> list[str]:
    with SessionLocal() as db:
        return UniverseMembershipRepository().get_latest_tickers(db, expected_counts)
