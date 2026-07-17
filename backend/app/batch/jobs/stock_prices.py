from __future__ import annotations

from app.batch.dates import normalize_yyyymmdd
from app.batch.retry import run_targets
from app.batch.targets import latest_universe_tickers
from app.batch.types import JobContext, JobResult, TargetResult
from app.db.session import SessionLocal
from app.services.instrument_price_service import InstrumentPriceService


def run_stock_prices(context: JobContext) -> JobResult:
    targets = context.targets or latest_universe_tickers(context)
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
