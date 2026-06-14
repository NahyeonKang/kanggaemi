"""
app/api/v1/endpoints/macro_indicator.py

Macro indicator API endpoints.
Prefix /macro is added by the main router.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.schemas.macro_indicator import (
    MacroObservationResponse,
    MacroSyncResponse,
)
from app.services.macro_indicator_service import MacroIndicatorService

router = APIRouter()


def get_macro_indicator_service() -> MacroIndicatorService:
    return MacroIndicatorService()


@router.post(
    "/core-market-indicators/sync",
    response_model=MacroSyncResponse,
    summary="Sync last 1 year of core market indicators from FRED",
)
def sync_core_market_indicators(
    db: Session = Depends(get_db),
    service: MacroIndicatorService = Depends(get_macro_indicator_service),
):
    return service.sync_last_1y_core_market_indicators(db)


@router.get(
    "/series",
    response_model=list[MacroObservationResponse],
    summary="Get stored macro indicator observations by series and date range",
)
def get_series(
    series_id: str,
    start_date: str,
    end_date: str,
    db: Session = Depends(get_db),
    service: MacroIndicatorService = Depends(get_macro_indicator_service),
):
    try:
        rows = service.get_series(
            db,
            series_id=series_id,
            start_date=start_date,
            end_date=end_date,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    return [
        MacroObservationResponse(
            source=r.source,
            series_id=r.series_id,
            observation_date=r.observation_date,
            value=r.value,
            fetched_at=r.fetched_at.isoformat(),
        )
        for r in rows
    ]