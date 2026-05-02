"""
app/api/v1/endpoints/exchange_rate.py

Exchange rate API endpoints.
Prefix /exchange-rate is added by the main router.
"""
import re

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.exchange_rate import (
    ExchangeRateQuoteResponse,
    ExchangeRateSyncRequest,
    ExchangeRateSyncResponse,
)
from app.services.exchange_rate_service import ExchangeRateService

router = APIRouter()


def get_exchange_rate_service() -> ExchangeRateService:
    return ExchangeRateService()


def _normalize_target_date(raw: str) -> str:
    """Accept YYYYMMDD or YYYY.MM.DD and return YYYY.MM.DD."""
    if re.fullmatch(r"\d{8}", raw):
        return f"{raw[:4]}.{raw[4:6]}.{raw[6:]}"
    if re.fullmatch(r"\d{4}\.\d{2}\.\d{2}", raw):
        return raw
    raise ValueError(
        f"target_date must be YYYYMMDD or YYYY.MM.DD, got: {raw!r}"
    )


@router.post(
    "/usdkrw/sync",
    response_model=ExchangeRateSyncResponse,
    summary="Sync USD/KRW quotes from KB Bank",
)
def sync_usdkrw_quotes(
    req: ExchangeRateSyncRequest,
    db: Session = Depends(get_db),
    service: ExchangeRateService = Depends(get_exchange_rate_service),
):
    """
    Scrape intraday USD/KRW quotes for the given date from KB Bank
    and upsert them into the database.
    """
    result = service.sync_usdkrw_quotes(db, search_date=req.search_date)
    return result


@router.get(
    "/usdkrw",
    response_model=list[ExchangeRateQuoteResponse],
    summary="Get stored USD/KRW quotes by date",
)
def get_usdkrw_quotes(
    target_date: str,
    db: Session = Depends(get_db),
    service: ExchangeRateService = Depends(get_exchange_rate_service),
):
    """
    Return all stored intraday quotes for a given date.
    Accepts target_date as YYYYMMDD or YYYY.MM.DD.
    """
    try:
        normalized = _normalize_target_date(target_date)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    rows = service.get_quotes(db, currency_code="USD", target_date=normalized)
    return [
        ExchangeRateQuoteResponse(
            source=r.source,
            currency_code=r.currency_code,
            target_date=r.target_date,
            quote_time=r.quote_time,
            base_rate=r.base_rate,
            fetched_at=r.fetched_at.isoformat(),
        )
        for r in rows
    ]
