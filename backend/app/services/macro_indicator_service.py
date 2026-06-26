"""
app/services/macro_indicator_service.py

매크로 지표 비즈니스 로직 (FRED). resolution(D/M) 인지.
monthly 시리즈가 추가되면 _SERIES_RESOLUTION 에만 등록하면 됨.
BOK 매크로를 붙일 땐 source/스크래퍼만 분기하면 테이블 변경 없이 확장.
"""
import logging
import re
from typing import Optional

from sqlalchemy.orm import Session

from app.models.macro_indicator import MacroObservationModel
from app.repositories.macro_indicator_repository import MacroIndicatorRepository
from app.schemas.macro_indicator import MacroSeriesSyncResult, MacroSyncResponse
from app.scrapers.fred.fred_scraper import FredScraper

logger = logging.getLogger(__name__)

TARGET_SERIES = ["DTWEXBGS", "T10YIE", "DFII10", "NASDAQSOX", "VIXCLS"]

# 시리즈별 resolution. 현재 전부 daily, monthly 추가 시 "M"으로 등록.
_SERIES_RESOLUTION: dict[str, str] = {s: "D" for s in TARGET_SERIES}

_ALLOWED_SERIES = frozenset(TARGET_SERIES)
_DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class MacroIndicatorService:
    def __init__(self) -> None:
        self._scraper = FredScraper()
        self._repo = MacroIndicatorRepository()

    def sync_core_indicators(self, db: Session) -> MacroSyncResponse:
        results: list[MacroSeriesSyncResult] = []
        for series_id in TARGET_SERIES:
            resolution = _SERIES_RESOLUTION[series_id]
            logger.info("Syncing FRED series %s (%s).", series_id, resolution)
            data = self._scraper.fetch_last_1y_series(series_id)
            rows = [(o.observation_date, o.value) for o in data.observations]
            affected = self._repo.upsert_observations(db, "fred", series_id, resolution, rows)
            dates = [d for d, _ in rows]
            results.append(
                MacroSeriesSyncResult(
                    series_id=series_id,
                    resolution=resolution,
                    affected_count=affected,
                    start_date=min(dates) if dates else None,
                    end_date=max(dates) if dates else None,
                )
            )
        return MacroSyncResponse(source="fred", series=results)

    def get_observations(
        self,
        db: Session,
        series_id: str,
        start_date: str,
        end_date: str,
        resolution: str = "D",
    ) -> list[MacroObservationModel]:
        self._validate_series_id(series_id)
        self._validate_date(start_date, "start_date")
        self._validate_date(end_date, "end_date")
        return self._repo.get_observations(db, series_id, start_date, end_date, resolution)

    # ── validations ──────────────────────────────────────────
    @staticmethod
    def _validate_series_id(series_id: str) -> None:
        if series_id not in _ALLOWED_SERIES:
            raise ValueError(
                f"series_id must be one of {sorted(_ALLOWED_SERIES)}, got: {series_id!r}"
            )

    @staticmethod
    def _validate_date(value: str, field_name: str) -> None:
        if not _DATE_PATTERN.match(value):
            raise ValueError(f"{field_name} must be YYYY-MM-DD, got: {value!r}")