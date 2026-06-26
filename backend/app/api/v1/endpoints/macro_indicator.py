"""
app/api/v1/endpoints/macro_indicator.py

Macro indicator API endpoints. Prefix는 메인 라우터에서 부여(예: /macro).
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.macro_indicator import MacroObservationResponse, MacroSyncResponse
from app.services.macro_indicator_service import MacroIndicatorService

router = APIRouter()


def get_macro_service() -> MacroIndicatorService:
    return MacroIndicatorService()


@router.post(
    "/sync",
    response_model=MacroSyncResponse,
    summary="Sync core macro indicators (FRED, last 1y)",
)
def sync_macro(
    db: Session = Depends(get_db),
    service: MacroIndicatorService = Depends(get_macro_service),
):
    return service.sync_core_indicators(db)


@router.get(
    "/observations",
    response_model=list[MacroObservationResponse],
    summary="Get stored macro observations by series and date range",
)
def get_macro_observations(
    series_id: str,
    start_date: str,
    end_date: str,
    resolution: str = "D",
    db: Session = Depends(get_db),
    service: MacroIndicatorService = Depends(get_macro_service),
):
    try:
        rows = service.get_observations(
            db, series_id=series_id, start_date=start_date,
            end_date=end_date, resolution=resolution,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return [MacroObservationResponse.model_validate(r) for r in rows]