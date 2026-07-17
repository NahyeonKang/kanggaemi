from __future__ import annotations

from app.batch.jobs.stock_prices import run_stock_prices
from app.batch.jobs.universe import run_universe_refresh
from app.batch.jobs.futures_master import run_futures_master_refresh
from app.batch.jobs.active_contracts import run_active_contract_refresh
from app.batch.jobs.futures_sync import run_futures_sync
from app.batch.jobs.market_level import run_market_level
from app.batch.jobs.stock_details import run_stock_details
from app.batch.types import JobHandler


HANDLERS: dict[str, JobHandler] = {
    "universe_refresh": run_universe_refresh,
    "stock_prices": run_stock_prices,
    "futures_master_refresh": run_futures_master_refresh,
    "active_contract_refresh": run_active_contract_refresh,
    "futures_sync": run_futures_sync,
    "market_level": run_market_level,
    "stock_details": run_stock_details,
}


def resolve_handler(name: str) -> JobHandler:
    try:
        return HANDLERS[name]
    except KeyError as exc:
        raise ValueError(f"unknown batch handler: {name}") from exc
