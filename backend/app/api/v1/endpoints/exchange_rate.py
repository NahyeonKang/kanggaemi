"""
app/api/v1/endpoints/exchange_rate.py

Exchange rate API endpoints.
Prefix /exchange-rate is added by the main router.
"""
from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.exchange_rate import (
    ExchangeRateSummarySyncRequest,
    ExchangeRateSummarySyncResponse,
    ExchangeRateSummaryResponse,
    ExchangeRateRangeSyncRequest,
    ExchangeRateRangeSyncResponse,
    ExchangeRateDailyResponse,
)
from app.services.exchange_rate_service import ExchangeRateService

router = APIRouter()

_KST = ZoneInfo("Asia/Seoul")


def get_exchange_rate_service() -> ExchangeRateService:
    return ExchangeRateService()


# ── 장중 스냅샷 ──────────────────────────────────────────────
@router.post(
    "/usdkrw/summary/sync",
    response_model=ExchangeRateSummarySyncResponse,
    summary="Sync USD/KRW intraday summary snapshot from KB Bank",
)
def sync_usdkrw_summary(
    req: ExchangeRateSummarySyncRequest,
    db: Session = Depends(get_db),
    service: ExchangeRateService = Depends(get_exchange_rate_service),
):
    try:
        return service.sync_usdkrw_summary(db, search_date=req.search_date)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@router.get(
    "/usdkrw/summary",
    response_model=ExchangeRateSummaryResponse,
    summary="Get latest stored USD/KRW snapshot for a date",
)
def get_usdkrw_summary(
    target_date: str,
    base_ccy: str = "USD",
    quote_ccy: str = "KRW",
    db: Session = Depends(get_db),
    service: ExchangeRateService = Depends(get_exchange_rate_service),
):
    try:
        row = service.get_latest_summary(
            db, target_date=target_date, base_ccy=base_ccy, quote_ccy=quote_ccy
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    if row is None:
        raise HTTPException(status_code=404, detail="Snapshot not found for date.")

    return ExchangeRateSummaryResponse.model_validate(row)


@router.get(
    "/usdkrw/summary/asof",
    response_model=ExchangeRateSummaryResponse,
    summary="Get point-in-time USD/KRW snapshot as of a given instant",
)
def get_usdkrw_summary_asof(
    target_date: str,
    as_of: datetime,                       # ISO 8601, 예: 2026-06-19T11:00:00+09:00
    base_ccy: str = "USD",
    quote_ccy: str = "KRW",
    db: Session = Depends(get_db),
    service: ExchangeRateService = Depends(get_exchange_rate_service),
):
    if as_of.tzinfo is None:               # naive 입력은 KST로 간주
        as_of = as_of.replace(tzinfo=_KST)
    try:
        row = service.get_summary_asof(
            db,
            target_date=target_date,
            as_of=as_of,
            base_ccy=base_ccy,
            quote_ccy=quote_ccy,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    if row is None:
        raise HTTPException(
            status_code=404, detail="No snapshot at or before as_of."
        )

    return ExchangeRateSummaryResponse.model_validate(row)


# ── 일별 종가 ────────────────────────────────────────────────
@router.post(
    "/usdkrw/daily/sync",
    response_model=ExchangeRateRangeSyncResponse,
    summary="Sync USD/KRW daily base-rate series from KB Bank",
)
def sync_usdkrw_daily(
    req: ExchangeRateRangeSyncRequest,
    db: Session = Depends(get_db),
    service: ExchangeRateService = Depends(get_exchange_rate_service),
):
    try:
        return service.sync_usdkrw_daily(
            db, start_date=req.start_date, end_date=req.end_date
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@router.get(
    "/usdkrw/daily",
    response_model=list[ExchangeRateDailyResponse],
    summary="Get stored USD/KRW daily quotes by date range",
)
def get_usdkrw_daily(
    start_date: str,
    end_date: str,
    base_ccy: str = "USD",
    quote_ccy: str = "KRW",
    db: Session = Depends(get_db),
    service: ExchangeRateService = Depends(get_exchange_rate_service),
):
    try:
        rows = service.get_daily(
            db,
            start_date=start_date,
            end_date=end_date,
            base_ccy=base_ccy,
            quote_ccy=quote_ccy,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    return [ExchangeRateDailyResponse.model_validate(r) for r in rows]