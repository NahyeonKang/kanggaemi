"""
app/services/macro_indicator_service.py

Business logic for FRED macro indicator data: fetching, persistence, and retrieval.
"""
import logging
from typing import Optional

from sqlalchemy.orm import Session

from app.models.macro_indicator import MacroIndicatorObservationModel
from app.repositories.macro_indicator_repository import MacroIndicatorRepository
from app.scrapers.fred.fred_macro_scraper import FredMacroScraper

logger = logging.getLogger(__name__)

TARGET_SERIES = ["DGS10", "DFII10", "NASDAQSOX", "VIXCLS"]


class MacroIndicatorService:
    """
    Orchestrates fetching, persistence, and retrieval of macro indicator observations.
    """

    def __init__(self) -> None:
        self._scraper = FredMacroScraper()
        self._repo = MacroIndicatorRepository()

    def sync_last_1w_core_market_indicators(self, db: Session) -> dict:
        """
        Fetch the last 1 week of observations for core FRED market indicators
        and upsert them into the database.

        Target series:
        - DGS10:     10-Year Treasury Constant Maturity Rate
        - DFII10:    10-Year Treasury Inflation-Indexed Security, Constant Maturity
        - NASDAQSOX: PHLX Semiconductor Index
        - VIXCLS:    CBOE Volatility Index: VIX

        Returns:
            Dict with source and per-series results:
            {
                "source": "fred",
                "series": [
                    {
                        "series_id": "...",
                        "affected_count": ...,
                        "start_date": "...",
                        "end_date": "..."
                    }
                ]
            }
        """
        results = []

        for series_id in TARGET_SERIES:
            logger.info("Syncing 1-week FRED series %s.", series_id)
            data = self._scraper.fetch_last_1w_series(series_id)
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
        """
        Return stored observations for a given series and date range.

        Args:
            db: SQLAlchemy session.
            series_id: FRED series identifier
                (e.g. "DGS10", "DFII10", "NASDAQSOX", "VIXCLS").
            start_date: Start date inclusive, YYYY-MM-DD.
            end_date: End date inclusive, YYYY-MM-DD.
        """
        return self._repo.get_series(db, series_id, start_date, end_date)