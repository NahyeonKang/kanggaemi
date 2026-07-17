"""
app/api/v1/endpoints/instrument_price.py

통합 시세 API. Prefix는 메인 라우터에서 부여(예: /price).
  - POST /sync                  : 국내 asset_class별 OHLCV + 스냅샷 적재
  - POST /overseas-futures/sync : 해외선물 일간 OHLCV 적재 (os_future)
  - GET  /ohlcv                 : OHLCV 시계열(asset_class; os_future 포함)
  - GET  /valuation[/asof]      : 주식 valuation
  - GET  /derivative[/asof]     : 국내 선물옵션 스냅샷
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


@router.post(
    "/overseas-futures/sync",
    response_model=ChartSyncResponse,
    summary="Sync overseas-futures daily OHLCV (os_future)",
)
def sync_overseas_futures(
    exch_cd: str,                        # 거래소코드 예: CME
    srs_cd: str,                         # 종목코드 예: 6AM24
    close_date: str,                     # 조회종료일 YYYYMMDD
    qry_cnt: int = 40,                   # 요청개수(최대 40)
    calc_decimal: Optional[int] = None,  # sCalcDesz(마스터). 미지정 시 raw
    currency: Optional[str] = None,      # 상품 통화(마스터)
    db: Session = Depends(get_db),
    service: InstrumentPriceService = Depends(get_price_service),
):
    try:
        return service.sync_overseas_futures(
            db, exch_cd=exch_cd, srs_cd=srs_cd, close_date=close_date,
            qry_cnt=qry_cnt, calc_decimal=calc_decimal, currency=currency,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@router.get("/ohlcv", response_model=list[OhlcvResponse], summary="Get stored OHLCV series")
def get_ohlcv(
    asset_class: str,                    # os_future의 entity_code는 "EXCH:SRS"
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


# ── 국내 선물옵션 스냅샷 ─────────────────────────────────────
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