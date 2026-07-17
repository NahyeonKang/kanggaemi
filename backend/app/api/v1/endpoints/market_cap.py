"""
app/api/v1/endpoints/market_cap.py

시총상위 API. Prefix는 메인 라우터에서 부여(예: /market-cap).
  - POST /sync : 시장별 시총 순위 스냅샷 적재
  - GET  /     : 저장된 순위 조회(top_n)
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.market_cap_ranking import MarketCapResponse, MarketCapSyncResponse
from app.services.market_cap_service import MarketCapService

router = APIRouter()


def get_market_cap_service() -> MarketCapService:
    return MarketCapService()


@router.post("/sync", response_model=MarketCapSyncResponse, summary="Sync market-cap ranking")
def sync_market_cap(
    market: str = "kospi",               # kospi | kosdaq | kospi200 | all
    div_cls_code: str = "0",             # 0전체 | 1보통주 | 2우선주
    top_n: Optional[int] = None,
    date: Optional[str] = None,          # YYYY-MM-DD
    db: Session = Depends(get_db),
    service: MarketCapService = Depends(get_market_cap_service),
):
    try:
        return service.sync_market_cap(
            db, market=market, div_cls_code=div_cls_code, top_n=top_n, date=date,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@router.get("", response_model=list[MarketCapResponse], summary="Get stored market-cap ranking")
def get_market_cap(
    market: str,
    observation_date: str,               # YYYY-MM-DD
    top_n: Optional[int] = None,
    db: Session = Depends(get_db),
    service: MarketCapService = Depends(get_market_cap_service),
):
    try:
        rows = service.get_market_cap(db, market, observation_date, top_n)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return [MarketCapResponse.model_validate(r) for r in rows]