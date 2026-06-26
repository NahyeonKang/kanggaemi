"""
app/api/v1/endpoints/yield_rate.py

Yield API endpoints. Prefix는 메인 라우터에서 부여(예: /yield).
  - daily 관측: /daily/sync, /daily/sync-all, /daily
  - intraday 스냅샷: /snapshot/sync, /snapshot, /snapshot/asof, /snapshots
"""
from datetime import datetime
from typing import Optional
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.yield_rate import YieldObservationResponse, YieldSnapshotResponse
from app.services.yield_service import YieldService

router = APIRouter()

_KST = ZoneInfo("Asia/Seoul")


def get_yield_service() -> YieldService:
    return YieldService()


# ── 관측 시계열 (daily) ──────────────────────────────────────
@router.post("/daily/sync", summary="Sync one (country, tenor) daily yield series")
def sync_yield_daily(
    country: str,
    tenor: str,
    db: Session = Depends(get_db),
    service: YieldService = Depends(get_yield_service),
):
    try:
        return service.sync_daily(db, country=country, tenor=tenor)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@router.post("/daily/sync-all", summary="Sync all configured daily yield series")
def sync_yield_daily_all(
    db: Session = Depends(get_db),
    service: YieldService = Depends(get_yield_service),
):
    return service.sync_all_daily(db)


@router.get(
    "/daily",
    response_model=list[YieldObservationResponse],
    summary="Get stored daily yields by (country, tenor) and date range",
)
def get_yield_daily(
    country: str,
    tenor: str,
    start_date: str,
    end_date: str,
    db: Session = Depends(get_db),
    service: YieldService = Depends(get_yield_service),
):
    try:
        rows = service.get_daily(
            db, country=country, tenor=tenor,
            start_date=start_date, end_date=end_date,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return [YieldObservationResponse.model_validate(r) for r in rows]


# ── 장중 스냅샷 ──────────────────────────────────────────────
@router.post("/snapshot/sync", summary="Sync KIS intraday yield snapshot (append)")
def sync_yield_snapshot(
    db: Session = Depends(get_db),
    service: YieldService = Depends(get_yield_service),
):
    return service.sync_snapshots(db)


@router.get(
    "/snapshot",
    response_model=YieldSnapshotResponse,
    summary="Get latest yield snapshot for (country, tenor)",
)
def get_yield_snapshot(
    country: str,
    tenor: str,
    db: Session = Depends(get_db),
    service: YieldService = Depends(get_yield_service),
):
    try:
        row = service.get_latest_snapshot(db, country=country, tenor=tenor)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    if row is None:
        raise HTTPException(status_code=404, detail="Snapshot not found.")
    return YieldSnapshotResponse.model_validate(row)


@router.get(
    "/snapshot/asof",
    response_model=YieldSnapshotResponse,
    summary="Get point-in-time yield snapshot as of a given instant",
)
def get_yield_snapshot_asof(
    country: str,
    tenor: str,
    as_of: datetime,
    db: Session = Depends(get_db),
    service: YieldService = Depends(get_yield_service),
):
    if as_of.tzinfo is None:
        as_of = as_of.replace(tzinfo=_KST)
    try:
        row = service.get_snapshot_asof(db, country=country, tenor=tenor, as_of=as_of)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    if row is None:
        raise HTTPException(status_code=404, detail="No snapshot at or before as_of.")
    return YieldSnapshotResponse.model_validate(row)


@router.get(
    "/snapshots",
    response_model=list[YieldSnapshotResponse],
    summary="List latest snapshot per (country, tenor)",
)
def list_yield_snapshots(
    country: Optional[str] = None,
    db: Session = Depends(get_db),
    service: YieldService = Depends(get_yield_service),
):
    rows = service.list_snapshots(db, country=country)
    return [YieldSnapshotResponse.model_validate(r) for r in rows]