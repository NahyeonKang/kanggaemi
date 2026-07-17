from __future__ import annotations

from datetime import datetime, timedelta

from app.batch.dates import KST, normalize_yyyymmdd
from app.batch.retry import run_targets
from app.batch.targets import selected_configured_targets
from app.batch.types import JobContext, JobResult, TargetResult
from app.db.session import SessionLocal
from app.services.exchange_rate_service import ExchangeRateService
from app.services.instrument_price_service import InstrumentPriceService
from app.services.investor_flow_service import InvestorFlowService
from app.services.macro_indicator_service import MacroIndicatorService
from app.services.market_funds_service import MarketFundsService
from app.services.program_trade_service import ProgramTradeService
from app.services.yield_service import YieldService


def run_market_level(context: JobContext) -> JobResult:
    operation = str(context.config["operation"])
    configured = {str(k): dict(v or {}) for k, v in context.config["targets"].items()}
    targets = selected_configured_targets(context, configured)
    since = normalize_yyyymmdd(context.since)
    date = normalize_yyyymmdd(context.date)
    if since and date and since > date:
        raise ValueError("--since must be on or before --date")

    if context.dry_run:
        return JobResult(
            job_name=context.job_name,
            targets=[TargetResult(
                target=target, success=True, attempts=0,
                output={
                    "dry_run": True, "operation": operation,
                    "since": since, "date": date, **configured[target],
                },
            ) for target in targets],
        )

    sync = _operation(operation, context, configured, since, date)
    return JobResult(
        job_name=context.job_name,
        targets=run_targets(context.job_name, targets, sync, context.retry_policy),
    )


def _operation(operation, context, configured, since, date):
    if operation == "index_chart":
        service = InstrumentPriceService()
        def sync(target):
            with SessionLocal() as db:
                return service.sync_chart(
                    db, asset_class="index", entity_code=configured[target]["entity_code"],
                    period=str(context.config.get("period", "D")),
                    start_date=since, end_date=date, adj=str(context.config.get("adj", "0")),
                )
        return sync
    if operation == "market_investor_flow":
        service = InvestorFlowService()
        def sync(target):
            values = configured[target]
            with SessionLocal() as db:
                return service.sync_market_daily(
                    db, market=values["market"],
                    sector_code=str(values["sector_code"]), date=date,
                )
        return sync
    if operation == "market_program_trade":
        service = ProgramTradeService()
        def sync(target):
            with SessionLocal() as db:
                return service.sync_market_daily(
                    db, market=configured[target]["market"], start_date=since, end_date=date,
                )
        return sync
    if operation == "market_funds":
        service = MarketFundsService()
        def sync(_target):
            with SessionLocal() as db:
                return service.sync_market_funds(db, date=date)
        return sync
    if operation == "macro_core":
        service = MacroIndicatorService()
        def sync(_target):
            with SessionLocal() as db:
                return service.sync_core_indicators(db).model_dump()
        return sync
    if operation == "yield_daily":
        service = YieldService()
        def sync(target):
            values = configured[target]
            with SessionLocal() as db:
                return service.sync_daily(db, values["country"], values["tenor"])
        return sync
    if operation == "exchange_rates":
        service = ExchangeRateService()
        end = date or datetime.now(KST).strftime("%Y%m%d")
        default_start = (datetime.strptime(end, "%Y%m%d") - timedelta(
            days=int(context.config.get("daily_lookback_days", 14))
        )).strftime("%Y%m%d")
        def sync(target):
            with SessionLocal() as db:
                return service.sync_usdkrw_daily(
                    db, start_date=since or default_start, end_date=end
                )
        return sync
    raise ValueError(f"unknown market-level operation: {operation}")
