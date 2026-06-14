"""
app/api/v1/endpoints/bok_bond_rate.py

BOK (Bank of Korea) historical bond rate API endpoints.
Prefix /bond-rate/history is added by the main router.
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.scrapers.bok.bok_bond_rate_scraper import ITEM_CODE_TREASURY_10Y
from app.schemas.bok_bond_rate import BOKBondRateResponse, BOKBondRateSyncResponse
from app.services.bok_bond_rate_service import BOKBondRateService

router = APIRouter()


def get_bok_bond_rate_service() -> BOKBondRateService:
    return BOKBondRateService()


@router.post(
    "/treasury-10y/sync",
    response_model=BOKBondRateSyncResponse,
    summary="Sync last 1 year of 10-year Korean treasury bond rates from BOK ECOS",
)
def sync_treasury_10y(
    db: Session = Depends(get_db),
    service: BOKBondRateService = Depends(get_bok_bond_rate_service),
):
    try:
        return service.sync_last_1y_treasury_10y(db)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@router.get(
    "/treasury-10y",
    response_model=list[BOKBondRateResponse],
    summary="Get stored 10-year Korean treasury bond rates",
)
def get_treasury_10y(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    db: Session = Depends(get_db),
    service: BOKBondRateService = Depends(get_bok_bond_rate_service),
):
    try:
        rows = service.get_rates(
            db,
            item_code=ITEM_CODE_TREASURY_10Y,
            start_date=start_date,
            end_date=end_date,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    return [
        BOKBondRateResponse(
            source=r.source,
            item_code=r.item_code,
            item_name=r.item_name,
            observation_date=r.observation_date,
            value=r.value,
            fetched_at=r.fetched_at.isoformat(),
        )
        for r in rows
    ]
