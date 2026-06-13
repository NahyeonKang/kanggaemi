"""
app/api/v1/endpoints/domestic_bond_rate.py

Domestic bond rate API endpoints.
Prefix /domestic-bond-rate is added by the main router.
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.domestic_bond_rate import (
    DomesticBondRateResponse,
    DomesticBondRateSyncRequest,
    DomesticBondRateSyncResponse,
)
from app.services.domestic_bond_rate_service import DomesticBondRateService

router = APIRouter()


def get_domestic_bond_rate_service() -> DomesticBondRateService:
    return DomesticBondRateService()


@router.post(
    "/sync",
    response_model=DomesticBondRateSyncResponse,
    summary="Sync domestic bond interest rates from KIS",
)
def sync_domestic_bond_rates(
    req: DomesticBondRateSyncRequest,
    db: Session = Depends(get_db),
    service: DomesticBondRateService = Depends(get_domestic_bond_rate_service),
):
    try:
        return service.sync_domestic_bond_rates(
            db,
            fid_cond_mrkt_div_code=req.fid_cond_mrkt_div_code,
            fid_cond_scr_div_code=req.fid_cond_scr_div_code,
            fid_div_cls_code=req.fid_div_cls_code,
            fid_div_cls_code1=req.fid_div_cls_code1,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@router.get(
    "/rates",
    response_model=list[DomesticBondRateResponse],
    summary="Get stored domestic bond interest rates",
)
def get_domestic_bond_rates(
    market_div_code: str,
    base_date: Optional[str] = None,
    db: Session = Depends(get_db),
    service: DomesticBondRateService = Depends(get_domestic_bond_rate_service),
):
    try:
        rows = service.get_rates(db, market_div_code=market_div_code, base_date=base_date)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    return [
        DomesticBondRateResponse(
            source=r.source,
            market_div_code=r.market_div_code,
            screen_div_code=r.screen_div_code,
            cls_code=r.cls_code,
            rate_code=r.rate_code,
            rate_name=r.rate_name,
            rate_value=r.rate_value,
            base_date=r.base_date,
            fetched_at=r.fetched_at.isoformat(),
        )
        for r in rows
    ]
