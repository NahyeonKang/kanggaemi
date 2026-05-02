"""
app/api/v1/endpoints/macro_indicator.py

Macro indicator API endpoints.
Prefix /macro is added by the main router.
"""
import re

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.macro_indicator import (
    MacroObservationResponse,
    MacroSyncResponse,
)
from app.services.macro_indicator_service import MacroIndicatorService, TARGET_SERIES

router = APIRouter()

_ALLOWED_SERIES = set(TARGET_SERIES)
_DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def get_macro_indicator_service() -> MacroIndicatorService:
    return MacroIndicatorService()


@router.post(
    "/core-market-indicators/sync",
    response_model=MacroSyncResponse,
    summary="Sync last 1 week of core market indicators from FRED",
)
def sync_core_market_indicators(
    db: Session = Depends(get_db),
    service: MacroIndicatorService = Depends(get_macro_indicator_service),
):
    """
    Fetch the last 7 days of core FRED market indicators and upsert them into the database.

    Target series:
    - DGS10
    - DFII10
    - NASDAQSOX
    - VIXCLS
    """
    return service.sync_last_1w_core_market_indicators(db)


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
    """
    Return stored observations for a given FRED series and date range.

    - **series_id**: One of DGS10, DFII10, NASDAQSOX, VIXCLS
    - **start_date**: Start date inclusive (YYYY-MM-DD)
    - **end_date**: End date inclusive (YYYY-MM-DD)
    """
    if series_id not in _ALLOWED_SERIES:
        raise HTTPException(
            status_code=422,
            detail=(
                f"series_id must be one of {sorted(_ALLOWED_SERIES)}, "
                f"got: {series_id!r}"
            ),
        )

    if not _DATE_PATTERN.match(start_date):
        raise HTTPException(
            status_code=422,
            detail=f"start_date must be YYYY-MM-DD, got: {start_date!r}",
        )

    if not _DATE_PATTERN.match(end_date):
        raise HTTPException(
            status_code=422,
            detail=f"end_date must be YYYY-MM-DD, got: {end_date!r}",
        )

    rows = service.get_series(
        db,
        series_id=series_id,
        start_date=start_date,
        end_date=end_date,
    )

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