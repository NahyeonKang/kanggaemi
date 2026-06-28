from fastapi import APIRouter
from app.api.v1.endpoints import health, exchange_rate, macro_indicator, yield_rate, investor_flow

api_router = APIRouter()
api_router.include_router(health.router, tags=["health"])
api_router.include_router(exchange_rate.router, prefix="/exchange-rate", tags=["exchange-rate"])
api_router.include_router(macro_indicator.router, prefix="/macro", tags=["macro"])
api_router.include_router(yield_rate.router, prefix="/yield", tags=["yield"])
api_router.include_router(investor_flow.router, prefix="/investor-flow", tags=["investor-flow"])