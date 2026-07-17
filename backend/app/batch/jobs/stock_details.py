from __future__ import annotations

import logging

from app.batch.dates import latest_completed_kr_business_date, normalize_yyyymmdd
from app.batch.retry import run_targets
from app.batch.targets import latest_universe_tickers
from app.batch.types import JobContext, JobResult, SkipTarget, TargetResult
from app.db.session import SessionLocal
from app.services.investor_flow_service import InvestorFlowService
from app.services.program_trade_service import ProgramTradeService
from app.services.stock_financials_service import StockFinancialsService


logger = logging.getLogger(__name__)


def run_stock_details(context: JobContext) -> JobResult:
    targets = list(dict.fromkeys(context.targets or latest_universe_tickers(context)))
    if not targets:
        raise RuntimeError("no stock targets; run universe-refresh first or pass --targets")
    operation = str(context.config["operation"])
    date = normalize_yyyymmdd(context.date)
    if date is None and operation in {"investor_flow", "program_trade"}:
        date = latest_completed_kr_business_date()
        logger.info(
            "stock_detail_effective_date_resolved",
            extra={
                "event": "stock_detail_effective_date_resolved",
                "job": context.job_name,
                "effective_date": date,
                "rule": "latest_kr_business_day_after_1540",
            },
        )

    if context.dry_run:
        return JobResult(
            job_name=context.job_name,
            targets=[TargetResult(
                target=ticker, success=True, attempts=0,
                output={"dry_run": True, "operation": operation, "date": date},
            ) for ticker in targets],
        )

    if operation == "financials":
        service = StockFinancialsService()

        def sync(ticker: str) -> dict:
            with SessionLocal() as db:
                results = [
                    service.sync_financials(db, ticker, str(div_cls_code))
                    for div_cls_code in context.config.get("div_cls_codes", ["0"])
                ]
                return {"ticker": ticker, "series": results}

    elif operation == "investor_flow":
        service = InvestorFlowService()
        endpoint_limit: dict | None = None

        def sync(ticker: str) -> dict:
            nonlocal endpoint_limit
            if endpoint_limit is not None:
                raise SkipTarget(
                    "endpoint_time_limit", details={"ticker": ticker, **endpoint_limit}
                )
            with SessionLocal() as db:
                try:
                    return service.sync_stock_daily(db, ticker=ticker, date=date)
                except ValueError as exc:
                    error_code = _configured_error_code(
                        str(exc), context.config.get("skip_time_limit_error_codes", [])
                    )
                    if error_code is None:
                        raise
                    endpoint_limit = {
                        "error_code": error_code,
                        "effective_date": date,
                        "first_observed_ticker": ticker,
                        "error_message": str(exc),
                    }
                    raise SkipTarget(
                        "endpoint_time_limit",
                        details={"ticker": ticker, **endpoint_limit},
                    ) from exc

    elif operation == "program_trade":
        service = ProgramTradeService()

        def sync(ticker: str) -> dict:
            with SessionLocal() as db:
                return service.sync_stock_daily(db, ticker=ticker, date=date)

    else:
        raise ValueError(f"unknown stock detail operation: {operation}")

    return JobResult(
        job_name=context.job_name,
        targets=run_targets(context.job_name, targets, sync, context.retry_policy),
    )


def _configured_error_code(message: str, configured_codes: list[str]) -> str | None:
    return next((str(code) for code in configured_codes if str(code) in message), None)
