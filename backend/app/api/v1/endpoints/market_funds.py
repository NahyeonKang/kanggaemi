"""
app/api/v1/endpoints/market_funds.py

증시자금 종합 API. Prefix는 메인 라우터에서 부여(예: /market-funds).
  - POST /sync : 기준일 이전 시계열 적재
  - GET  /     : 저장된 증시자금 시계열 조회
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.market_funds import MarketFundsResponse, MarketFundsSyncResponse
from app.services.market_funds_service import MarketFundsService

router = APIRouter()


def get_market_funds_service() -> MarketFundsService:
    return MarketFundsService()


@router.post("/sync", response_model=MarketFundsSyncResponse, summary="Sync market funds")
def sync_market_funds(
    date: Optional[str] = None,          # YYYYMMDD (기준일, 생략 시 오늘)
    db: Session = Depends(get_db),
    service: MarketFundsService = Depends(get_market_funds_service),
):
    try:
        return service.sync_market_funds(db, date=date)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@router.get("", response_model=list[MarketFundsResponse], summary="Get stored market funds")
def get_market_funds(
    start_date: str,
    end_date: str,
    db: Session = Depends(get_db),
    service: MarketFundsService = Depends(get_market_funds_service),
):
    try:
        rows = service.get_market_funds(db, start_date=start_date, end_date=end_date)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return [MarketFundsResponse.model_validate(r) for r in rows]