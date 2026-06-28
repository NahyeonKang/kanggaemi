"""
app/api/v1/endpoints/investor_flow.py

수급(투자자별 매매동향 일별) API. Prefix는 메인 라우터에서 부여(예: /flow).
  - 시장: /market/sync, /market
  - 종목: /stock/sync, /stock
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.investor_flow import InvestorFlowResponse, InvestorFlowSyncResponse
from app.services.investor_flow_service import InvestorFlowService

router = APIRouter()


def get_flow_service() -> InvestorFlowService:
    return InvestorFlowService()


# ── 시장별 ───────────────────────────────────────────────────
@router.post(
    "/market/sync",
    response_model=InvestorFlowSyncResponse,
    summary="Sync market investor flow (KOSPI/KOSDAQ, daily)",
)
def sync_market_flow(
    market: str,
    sector_code: str = "0001",
    date: Optional[str] = None,          # YYYYMMDD
    db: Session = Depends(get_db),
    service: InvestorFlowService = Depends(get_flow_service),
):
    try:
        return service.sync_market_daily(db, market=market, sector_code=sector_code, date=date)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@router.get(
    "/market",
    response_model=list[InvestorFlowResponse],
    summary="Get stored market investor flow",
)
def get_market_flow(
    market: str,
    start_date: str,
    end_date: str,
    investor_type: Optional[str] = None,
    sector_code: str = "0001",
    db: Session = Depends(get_db),
    service: InvestorFlowService = Depends(get_flow_service),
):
    try:
        rows = service.get_market_flow(
            db, market=market, start_date=start_date, end_date=end_date,
            investor_type=investor_type, sector_code=sector_code,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return [InvestorFlowResponse.model_validate(r) for r in rows]


# ── 종목별 ───────────────────────────────────────────────────
@router.post(
    "/stock/sync",
    response_model=InvestorFlowSyncResponse,
    summary="Sync stock investor flow (daily)",
)
def sync_stock_flow(
    ticker: str,
    date: Optional[str] = None,          # YYYYMMDD
    db: Session = Depends(get_db),
    service: InvestorFlowService = Depends(get_flow_service),
):
    try:
        return service.sync_stock_daily(db, ticker=ticker, date=date)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@router.get(
    "/stock",
    response_model=list[InvestorFlowResponse],
    summary="Get stored stock investor flow",
)
def get_stock_flow(
    ticker: str,
    start_date: str,
    end_date: str,
    investor_type: Optional[str] = None,
    db: Session = Depends(get_db),
    service: InvestorFlowService = Depends(get_flow_service),
):
    try:
        rows = service.get_stock_flow(
            db, ticker=ticker, start_date=start_date,
            end_date=end_date, investor_type=investor_type,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return [InvestorFlowResponse.model_validate(r) for r in rows]