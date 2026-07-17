"""
app/api/v1/endpoints/stock_financials.py

개별 종목 재무 API. Prefix는 메인 라우터에서 부여(예: /financials).
  - POST /sync : 4개 재무 API 병합 적재
  - GET  /     : 저장된 재무 시계열 조회
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.stock_financials import FinancialsResponse, FinancialsSyncResponse
from app.services.stock_financials_service import StockFinancialsService

router = APIRouter()


def get_financials_service() -> StockFinancialsService:
    return StockFinancialsService()


@router.post("/sync", response_model=FinancialsSyncResponse, summary="Sync stock financials (4 APIs merged)")
def sync_financials(
    ticker: str,
    div_cls_code: str = "0",              # 0=년, 1=분기(연누적)
    db: Session = Depends(get_db),
    service: StockFinancialsService = Depends(get_financials_service),
):
    try:
        return service.sync_financials(db, ticker=ticker, div_cls_code=div_cls_code)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@router.get("", response_model=list[FinancialsResponse], summary="Get stored financials")
def get_financials(
    ticker: str,
    period_type: str = "annual",          # annual | quarter
    start_yymm: Optional[str] = None,     # YYYYMM
    end_yymm: Optional[str] = None,       # YYYYMM
    db: Session = Depends(get_db),
    service: StockFinancialsService = Depends(get_financials_service),
):
    try:
        rows = service.get_financials(
            db, ticker=ticker, period_type=period_type,
            start_yymm=start_yymm, end_yymm=end_yymm,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return [FinancialsResponse.model_validate(r) for r in rows]