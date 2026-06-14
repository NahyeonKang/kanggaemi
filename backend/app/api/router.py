from fastapi import APIRouter
from app.api.v1.endpoints import health, exchange_rate, macro_indicator, yield_daily, yield_snapshot

api_router = APIRouter()
api_router.include_router(health.router, tags=["health"])
api_router.include_router(exchange_rate.router, prefix="/exchange-rate", tags=["exchange-rate"])
api_router.include_router(macro_indicator.router, prefix="/macro", tags=["macro"])
api_router.include_router(yield_daily.router, prefix="/yield/daily", tags=["yield-daily"])
api_router.include_router(yield_snapshot.router, prefix="/yield/snapshot", tags=["yield-snapshot"])