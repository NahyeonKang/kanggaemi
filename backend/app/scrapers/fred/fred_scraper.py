"""
app/scrapers/fred/fred_scraper.py

Generic scraper for the FRED (Federal Reserve Economic Data) API.

Shared by the macro indicator domain (DFII10, NASDAQSOX, VIXCLS) and the
yield domain (US daily yields: SOFR, DGS2, DGS10, DGS30) via the same
generic fetch_series(series_id, days).
"""
from datetime import date, datetime, timedelta
from typing import Optional

import requests

from app.core.config import settings
from app.schemas.macro_indicator import FredObservation, FredSeriesData

_FRED_BASE_URL = "https://api.stlouisfed.org/fred/series/observations"
_TIMEOUT = 20


def _utc_now_iso() -> str:
    return datetime.utcnow().isoformat()


class FredScraper:
    """
    Fetches observation series from the FRED API.

    Requires FRED_API_KEY to be set as an environment variable.
    """

    def __init__(self, api_key: Optional[str] = None, timeout: int = _TIMEOUT) -> None:
        self.api_key = api_key or settings.FRED_API_KEY
        if not self.api_key:
            raise ValueError(
                "FRED_API_KEY is not set. "
                "Add it to .env or pass it explicitly."
            )

        self.timeout = timeout
        self._session = requests.Session()
        self._session.headers.update(
            {
                "User-Agent": "Mozilla/5.0",
                "Accept": "application/json",
            }
        )

    def fetch_series(self, series_id: str, days: int = 365) -> FredSeriesData:
        """
        Fetch observations for the past N days from FRED.

        Args:
            series_id: FRED series identifier (e.g. "DGS10", "DFII10", "SOFR").
            days: number of days of history to fetch.

        Returns:
            FredSeriesData with observations in ascending date order.

        Raises:
            requests.HTTPError: If the API returns a non-2xx status.
        """
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

        response = self._session.get(
            _FRED_BASE_URL,
            params=params,
            timeout=self.timeout,
        )
        response.raise_for_status()

        raw_obs = response.json().get("observations", [])
        fetched_at = _utc_now_iso()

        observations: list[FredObservation] = []

        for row in raw_obs:
            raw_value = row.get("value")

            value: Optional[float] = None
            if raw_value not in (None, ".", ""):
                try:
                    value = float(raw_value)
                except (TypeError, ValueError):
                    pass

            observations.append(
                FredObservation(
                    series_id=series_id,
                    observation_date=row["date"],
                    value=value,
                    fetched_at=fetched_at,
                )
            )

        return FredSeriesData(
            series_id=series_id,
            observations=observations,
            fetched_at=fetched_at,
        )

    # ---- convenience wrappers ----

    def fetch_last_1w_series(self, series_id: str) -> FredSeriesData:
        """Fetch last 7 days of observations."""
        return self.fetch_series(series_id, days=7)

    def fetch_last_1y_series(self, series_id: str) -> FredSeriesData:
        """Fetch last 365 days of observations."""
        return self.fetch_series(series_id, days=365)
