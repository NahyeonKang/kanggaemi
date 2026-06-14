"""
app/services/bok_bond_rate_service.py

Business logic for BOK (Bank of Korea) ECOS historical bond rate data:
fetching, persistence, and retrieval.
"""
import logging
import re
from typing import Optional

from sqlalchemy.orm import Session

from app.models.bok_bond_rate import BOKBondRateModel
from app.repositories.bok_bond_rate_repository import BOKBondRateRepository
from app.scrapers.bok.bok_bond_rate_scraper import BOKBondRateScraper

logger = logging.getLogger(__name__)

_DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class BOKBondRateService:
    def __init__(self) -> None:
        self._scraper = BOKBondRateScraper()
        self._repo = BOKBondRateRepository()

    def sync_last_1y_treasury_10y(self, db: Session) -> dict:
        logger.info("Syncing last 1 year of BOK 10-year treasury bond rates.")

        data = self._scraper.fetch_last_1y_treasury_10y()
        affected = self._repo.upsert_rates(db, data)

        dates = [item.observation_date for item in data.items]
        start_date = min(dates) if dates else None
        end_date = max(dates) if dates else None

        return {
            "source": data.source,
            "item_code": data.item_code,
            "affected_count": affected,
            "start_date": start_date,
            "end_date": end_date,
        }

    def get_rates(
        self,
        db: Session,
        item_code: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> list[BOKBondRateModel]:
        if start_date is not None:
            self._validate_date(start_date, "start_date")
        if end_date is not None:
            self._validate_date(end_date, "end_date")
        return self._repo.get_rates(db, item_code, start_date, end_date)

    # ------------------------------------------------------------------ #
    # Private helpers                                                      #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _validate_date(value: str, field_name: str) -> None:
        if not _DATE_PATTERN.match(value):
            raise ValueError(f"{field_name} must be YYYY-MM-DD, got: {value!r}")
