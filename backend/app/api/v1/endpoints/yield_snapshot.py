"""
app/api/v1/endpoints/yield_snapshot.py

Yield snapshot (latest KIS comp-interest) API endpoints.
Prefix /yield/snapshot is added by the main router.
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.yield_rate import YieldSnapshotResponse, YieldSnapshotSyncResponse
from app.services.yield_service import YieldService

router = APIRouter()


def get_yield_service() -> YieldService:
    return YieldService()


@router.post(
    "/sync",
    response_model=YieldSnapshotSyncResponse,
    summary="Sync the latest KIS comp-interest snapshot for all known tenors",
)
def sync_snapshots(
    db: Session = Depends(get_db),
    service: YieldService = Depends(get_yield_service),
):
    try:
        return service.sync_snapshots(db)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@router.get(
    "/",
    response_model=YieldSnapshotResponse,
    summary="Get the latest snapshot for one (country, tenor)",
)
def get_snapshot(
    country: str,
    tenor: str,
    db: Session = Depends(get_db),
    service: YieldService = Depends(get_yield_service),
):
    try:
        row = service.get_snapshot(db, country=country, tenor=tenor)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    if row is None:
        raise HTTPException(status_code=404, detail="Snapshot not found.")

    return YieldSnapshotResponse(
        country=row.country,
        tenor=row.tenor,
        current_rate=row.current_rate,
        prdy_vrss_sign=row.prdy_vrss_sign,
        prdy_vrss=row.prdy_vrss,
        prdy_ctrt=row.prdy_ctrt,
        base_date=row.base_date,
        source=row.source,
        fetched_at=row.fetched_at.isoformat(),
    )


@router.get(
    "/all",
    response_model=list[YieldSnapshotResponse],
    summary="Get all latest snapshots, optionally filtered by country",
)
def list_snapshots(
    country: Optional[str] = None,
    db: Session = Depends(get_db),
    service: YieldService = Depends(get_yield_service),
):
    rows = service.list_snapshots(db, country=country)
    return [
        YieldSnapshotResponse(
            country=r.country,
            tenor=r.tenor,
            current_rate=r.current_rate,
            prdy_vrss_sign=r.prdy_vrss_sign,
            prdy_vrss=r.prdy_vrss,
            prdy_ctrt=r.prdy_ctrt,
            base_date=r.base_date,
            source=r.source,
            fetched_at=r.fetched_at.isoformat(),
        )
        for r in rows
    ]
