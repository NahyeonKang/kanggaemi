"""
app/api/v1/endpoints/yield_daily.py

Yield daily (official daily close) API endpoints.
Prefix /yield/daily is added by the main router.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.yield_rate import (
    YieldDailyResponse,
    YieldDailySyncAllResponse,
    YieldDailySyncRequest,
    YieldDailySyncResponse,
)
from app.services.yield_service import YieldService

router = APIRouter()


def get_yield_service() -> YieldService:
    return YieldService()


@router.post(
    "/sync",
    response_model=YieldDailySyncResponse,
    summary="Sync last 1 year of daily close yields for one (country, tenor)",
)
def sync_daily(
    req: YieldDailySyncRequest,
    db: Session = Depends(get_db),
    service: YieldService = Depends(get_yield_service),
):
    try:
        return service.sync_daily(db, country=req.country, tenor=req.tenor)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@router.post(
    "/sync-all",
    response_model=YieldDailySyncAllResponse,
    summary="Sync last 1 year of daily close yields for all known (country, tenor) pairs",
)
def sync_all_daily(
    db: Session = Depends(get_db),
    service: YieldService = Depends(get_yield_service),
):
    return service.sync_all_daily(db)


@router.get(
    "/",
    response_model=list[YieldDailyResponse],
    summary="Get stored daily close yields for one (country, tenor) and date range",
)
def get_daily(
    country: str,
    tenor: str,
    start_date: str,
    end_date: str,
    db: Session = Depends(get_db),
    service: YieldService = Depends(get_yield_service),
):
    try:
        rows = service.get_daily(
            db,
            country=country,
            tenor=tenor,
            start_date=start_date,
            end_date=end_date,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    return [
        YieldDailyResponse(
            country=r.country,
            tenor=r.tenor,
            d=r.d,
            close=r.close,
            source=r.source,
            ingested_at=r.ingested_at.isoformat(),
        )
        for r in rows
    ]
