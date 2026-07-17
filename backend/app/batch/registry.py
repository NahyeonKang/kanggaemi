from __future__ import annotations

from app.batch.jobs.stock_prices import run_stock_prices
from app.batch.jobs.universe import run_universe_refresh
from app.batch.types import JobHandler


HANDLERS: dict[str, JobHandler] = {
    "universe_refresh": run_universe_refresh,
    "stock_prices": run_stock_prices,
}


def resolve_handler(name: str) -> JobHandler:
    try:
        return HANDLERS[name]
    except KeyError as exc:
        raise ValueError(f"unknown batch handler: {name}") from exc

