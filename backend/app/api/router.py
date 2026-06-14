from fastapi import APIRouter
from app.api.v1.endpoints import health, exchange_rate, macro_indicator, domestic_bond_rate, bok_bond_rate

api_router = APIRouter()
api_router.include_router(health.router, tags=["health"])
api_router.include_router(exchange_rate.router, prefix="/exchange-rate", tags=["exchange-rate"])
api_router.include_router(macro_indicator.router, prefix="/macro", tags=["macro"])
api_router.include_router(domestic_bond_rate.router, prefix="/domestic-bond-rate", tags=["domestic-bond-rate"])
api_router.include_router(bok_bond_rate.router, prefix="/bond-rate/history", tags=["bond-rate-history"])