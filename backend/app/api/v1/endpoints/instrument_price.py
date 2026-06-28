"""
app/api/v1/endpoints/instrument_price.py

통합 시세 API. Prefix는 메인 라우터에서 부여(예: /price).
  - POST /sync            : asset_class별 OHLCV + 스냅샷 적재
  - GET  /ohlcv           : OHLCV 시계열(asset_class)
  - GET  /valuation       : 주식 최신 valuation
  - GET  /valuation/asof  : 주식 point-in-time valuation
  - GET  /derivative      : 선물옵션 최신 스냅샷
  - GET  /derivative/asof : 선물옵션 point-in-time 스냅샷
"""
from datetime import datetime
from typing import Optional
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.instrument_price import (
    OhlcvResponse, StockValuationResponse, DerivativeSnapshotResponse, ChartSyncResponse,
)
from app.services.instrument_price_service import InstrumentPriceService

router = APIRouter()

_KST = ZoneInfo("Asia/Seoul")


def get_price_service() -> InstrumentPriceService:
    return InstrumentPriceService()


@router.post("/sync", response_model=ChartSyncResponse, summary="Sync period OHLCV + snapshot")
def sync_chart(
    asset_class: str,                    # stock | index | future | option
    entity_code: str,
    period: str = "D",
    start_date: Optional[str] = None,    # YYYYMMDD
    end_date: Optional[str] = None,      # YYYYMMDD
    adj: str = "0",
    db: Session = Depends(get_db),
    service: InstrumentPriceService = Depends(get_price_service),
):
    try:
        return service.sync_chart(
            db, asset_class=asset_class, entity_code=entity_code, period=period,
            start_date=start_date, end_date=end_date, adj=adj,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@router.get("/ohlcv", response_model=list[OhlcvResponse], summary="Get stored OHLCV series")
def get_ohlcv(
    asset_class: str,
    entity_code: str,
    resolution: str,
    start_date: str,
    end_date: str,
    db: Session = Depends(get_db),
    service: InstrumentPriceService = Depends(get_price_service),
):
    try:
        rows = service.get_ohlcv(db, asset_class, entity_code, resolution, start_date, end_date)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return [OhlcvResponse.model_validate(r) for r in rows]


# ── 주식 valuation ───────────────────────────────────────────
@router.get("/valuation", response_model=StockValuationResponse, summary="Latest stock valuation")
def get_valuation(
    ticker: str,
    db: Session = Depends(get_db),
    service: InstrumentPriceService = Depends(get_price_service),
):
    row = service.get_latest_valuation(db, ticker)
    if row is None:
        raise HTTPException(status_code=404, detail="Valuation snapshot not found.")
    return StockValuationResponse.model_validate(row)


@router.get("/valuation/asof", response_model=StockValuationResponse, summary="Point-in-time stock valuation")
def get_valuation_asof(
    ticker: str,
    as_of: datetime,
    db: Session = Depends(get_db),
    service: InstrumentPriceService = Depends(get_price_service),
):
    if as_of.tzinfo is None:
        as_of = as_of.replace(tzinfo=_KST)
    row = service.get_valuation_asof(db, ticker, as_of)
    if row is None:
        raise HTTPException(status_code=404, detail="No valuation at or before as_of.")
    return StockValuationResponse.model_validate(row)


# ── 선물옵션 스냅샷 ──────────────────────────────────────────
@router.get("/derivative", response_model=DerivativeSnapshotResponse, summary="Latest derivative snapshot")
def get_derivative(
    entity_code: str,
    db: Session = Depends(get_db),
    service: InstrumentPriceService = Depends(get_price_service),
):
    row = service.get_latest_derivative(db, entity_code)
    if row is None:
        raise HTTPException(status_code=404, detail="Derivative snapshot not found.")
    return DerivativeSnapshotResponse.model_validate(row)


@router.get("/derivative/asof", response_model=DerivativeSnapshotResponse, summary="Point-in-time derivative snapshot")
def get_derivative_asof(
    entity_code: str,
    as_of: datetime,
    db: Session = Depends(get_db),
    service: InstrumentPriceService = Depends(get_price_service),
):
    if as_of.tzinfo is None:
        as_of = as_of.replace(tzinfo=_KST)
    row = service.get_derivative_asof(db, entity_code, as_of)
    if row is None:
        raise HTTPException(status_code=404, detail="No derivative snapshot at or before as_of.")
    return DerivativeSnapshotResponse.model_validate(row)