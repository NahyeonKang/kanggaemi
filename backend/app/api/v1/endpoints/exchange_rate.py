"""
app/api/v1/endpoints/exchange_rate.py

Exchange rate API endpoints.
Prefix /exchange-rate is added by the main router.
"""
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


def get_exchange_rate_service() -> ExchangeRateService:
    return ExchangeRateService()


# ── 장중 요약 ────────────────────────────────────────────────
@router.post(
    "/usdkrw/summary/sync",
    response_model=ExchangeRateSummarySyncResponse,
    summary="Sync USD/KRW intraday summary from KB Bank",
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
    summary="Get stored USD/KRW intraday summary by date",
)
def get_usdkrw_summary(
    target_date: str,
    db: Session = Depends(get_db),
    service: ExchangeRateService = Depends(get_exchange_rate_service),
):
    try:
        row = service.get_summary(db, currency_code="USD", target_date=target_date)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    if row is None:
        raise HTTPException(status_code=404, detail="Summary not found for date.")

    return ExchangeRateSummaryResponse(
        source=row.source,
        currency_code=row.currency_code,
        target_date=row.target_date,
        first_rate=row.first_rate,
        last_rate=row.last_rate,
        daily_low=row.daily_low,
        daily_high=row.daily_high,
        daily_avg=row.daily_avg,
        fetched_at=row.fetched_at.isoformat(),
    )


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
    db: Session = Depends(get_db),
    service: ExchangeRateService = Depends(get_exchange_rate_service),
):
    try:
        rows = service.get_daily(
            db, currency_code="USD", start_date=start_date, end_date=end_date
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    return [
        ExchangeRateDailyResponse(
            source=r.source,
            currency_code=r.currency_code,
            quote_date=r.quote_date,
            base_rate=r.base_rate,
            fetched_at=r.fetched_at.isoformat(),
        )
        for r in rows
    ]