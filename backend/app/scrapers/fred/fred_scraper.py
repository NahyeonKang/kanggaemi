"""
app/scrapers/fred/fred_scraper.py

Generic FRED API scraper. macro·yield 양쪽에서 fetch_series(series_id, days) 공용.
"""
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Optional
from zoneinfo import ZoneInfo

import requests

from app.core.config import settings
from app.schemas.macro_indicator import FredObservation, FredSeriesData

_FRED_BASE_URL = "https://api.stlouisfed.org/fred/series/observations"
_TIMEOUT = 20
_KST = ZoneInfo("Asia/Seoul")


def _to_decimal(raw: Optional[str]) -> Optional[Decimal]:
    if raw in (None, ".", ""):
        return None
    try:
        return Decimal(str(raw))
    except (InvalidOperation, ValueError):
        return None


class FredScraper:
    """Fetches observation series from the FRED API. Requires FRED_API_KEY."""

    def __init__(self, api_key: Optional[str] = None, timeout: int = _TIMEOUT) -> None:
        self.api_key = api_key or settings.FRED_API_KEY
        if not self.api_key:
            raise ValueError("FRED_API_KEY is not set. Add it to .env or pass it explicitly.")

        self.timeout = timeout
        self._session = requests.Session()
        self._session.headers.update(
            {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}
        )

    def fetch_series(self, series_id: str, days: int = 365) -> FredSeriesData:
        """Fetch observations for the past N days. Ascending date order."""
        today = date.today()
        start_date = today - timedelta(days=days)

        params = {
            "series_id": series_id,
            "api_key": self.api_key,
            "file_type": "json",
            "sort_order": "asc",
            "observation_start": start_date.strftime("%Y-%m-%d"),
            "observation_end": today.strftime("%Y-%m-%d"),
        }

        response = self._session.get(_FRED_BASE_URL, params=params, timeout=self.timeout)
        response.raise_for_status()

        raw_obs = response.json().get("observations", [])
        observed_at = datetime.now(_KST)

        observations = [
            FredObservation(
                observation_date=row["date"],
                value=_to_decimal(row.get("value")),
            )
            for row in raw_obs
        ]

        return FredSeriesData(
            source="fred",
            series_id=series_id,
            observed_at=observed_at,
            observations=observations,
        )

    def fetch_last_1y_series(self, series_id: str) -> FredSeriesData:
        return self.fetch_series(series_id, days=365)
