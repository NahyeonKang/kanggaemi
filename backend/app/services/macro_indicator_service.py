"""
app/services/macro_indicator_service.py

Business logic for FRED macro indicator data: fetching, persistence, and retrieval.
"""
import logging
import re
from typing import Optional
from sqlalchemy.orm import Session
from app.models.macro_indicator import MacroIndicatorObservationModel
from app.repositories.macro_indicator_repository import MacroIndicatorRepository
from app.scrapers.fred.fred_scraper import FredScraper

logger = logging.getLogger(__name__)

# DGS10 (US 10Y) lives in the yield domain as yield_daily ('US', '10Y').
# TODO: DFII10 (US 10Y real/TIPS) may move to yield_daily as ('US', '10Y_REAL').
TARGET_SERIES = ["DFII10", "NASDAQSOX", "VIXCLS"]

_ALLOWED_SERIES = frozenset(TARGET_SERIES)
_DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class MacroIndicatorService:
    def __init__(self) -> None:
        self._scraper = FredScraper()
        self._repo = MacroIndicatorRepository()

    def sync_last_1y_core_market_indicators(self, db: Session) -> dict:
        results = []
        for series_id in TARGET_SERIES:
            logger.info("Syncing 1-year FRED series %s.", series_id)
            data = self._scraper.fetch_last_1y_series(series_id)
            affected = self._repo.upsert_series_data(db, data)
            dates = [obs.observation_date for obs in data.observations]
            start_date: Optional[str] = min(dates) if dates else None
            end_date: Optional[str] = max(dates) if dates else None
            results.append(
                {
                    "series_id": series_id,
                    "affected_count": affected,
                    "start_date": start_date,
                    "end_date": end_date,
                }
            )
        return {"source": "fred", "series": results}

    def get_series(
        self,
        db: Session,
        series_id: str,
        start_date: str,
        end_date: str,
    ) -> list[MacroIndicatorObservationModel]:
        self._validate_series_id(series_id)
        self._validate_date(start_date, "start_date")
        self._validate_date(end_date, "end_date")
        return self._repo.get_series(db, series_id, start_date, end_date)

    # ------------------------------------------------------------------ #
    # Private helpers                                                      #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _validate_series_id(series_id: str) -> None:
        if series_id not in _ALLOWED_SERIES:
            raise ValueError(
                f"series_id must be one of {sorted(_ALLOWED_SERIES)}, "
                f"got: {series_id!r}"
            )

    @staticmethod
    def _validate_date(value: str, field_name: str) -> None:
        if not _DATE_PATTERN.match(value):
            raise ValueError(
                f"{field_name} must be YYYY-MM-DD, got: {value!r}"
            )