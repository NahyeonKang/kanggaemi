"""
app/api/v1/endpoints/program_trade.py

프로그램매매 추이(일별) API. Prefix는 메인 라우터에서 부여(예: /program).
  - 시장: /market/sync, /market
  - 종목: /stock/sync, /stock
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.program_trade import ProgramTradeResponse, ProgramTradeSyncResponse
from app.services.program_trade_service import ProgramTradeService

router = APIRouter()


def get_program_service() -> ProgramTradeService:
    return ProgramTradeService()


# ── 시장별 ───────────────────────────────────────────────────
@router.post(
    "/market/sync",
    response_model=ProgramTradeSyncResponse,
    summary="Sync market program trade (KOSPI/KOSDAQ, daily)",
)
def sync_market_program(
    market: str,
    start_date: Optional[str] = None,    # YYYYMMDD
    end_date: Optional[str] = None,      # YYYYMMDD
    db: Session = Depends(get_db),
    service: ProgramTradeService = Depends(get_program_service),
):
    try:
        return service.sync_market_daily(db, market=market, start_date=start_date, end_date=end_date)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@router.get(
    "/market",
    response_model=list[ProgramTradeResponse],
    summary="Get stored market program trade",
)
def get_market_program(
    market: str,
    start_date: str,
    end_date: str,
    trade_class: Optional[str] = None,
    account_type: Optional[str] = None,
    db: Session = Depends(get_db),
    service: ProgramTradeService = Depends(get_program_service),
):
    try:
        rows = service.get_market_trade(
            db, market=market, start_date=start_date, end_date=end_date,
            trade_class=trade_class, account_type=account_type,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return [ProgramTradeResponse.model_validate(r) for r in rows]


# ── 종목별 ───────────────────────────────────────────────────
@router.post(
    "/stock/sync",
    response_model=ProgramTradeSyncResponse,
    summary="Sync stock program trade (daily)",
)
def sync_stock_program(
    ticker: str,
    date: Optional[str] = None,          # YYYYMMDD
    db: Session = Depends(get_db),
    service: ProgramTradeService = Depends(get_program_service),
):
    try:
        return service.sync_stock_daily(db, ticker=ticker, date=date)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@router.get(
    "/stock",
    response_model=list[ProgramTradeResponse],
    summary="Get stored stock program trade",
)
def get_stock_program(
    ticker: str,
    start_date: str,
    end_date: str,
    db: Session = Depends(get_db),
    service: ProgramTradeService = Depends(get_program_service),
):
    try:
        rows = service.get_stock_trade(
            db, ticker=ticker, start_date=start_date, end_date=end_date,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return [ProgramTradeResponse.model_validate(r) for r in rows]