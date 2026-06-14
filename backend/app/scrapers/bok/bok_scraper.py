"""
app/scrapers/bok/bok_scraper.py

Generic scraper for the Bank of Korea (BOK) ECOS StatisticSearch API.

Used by the yield domain to fetch KR daily yields (817Y002 / D / item_code)
for any (stat_code, item_code, period) combination.
"""
import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import requests

from app.core.config import settings
from app.schemas.yield_rate import BOKSeriesData, BOKSeriesObservation

logger = logging.getLogger(__name__)

_ECOS_BASE_URL = "https://ecos.bok.or.kr/api/StatisticSearch"
_TIMEOUT = 20
_PAGE_SIZE = 100


class BOKScraper:
    """
    Fetches statistical series from the BOK ECOS StatisticSearch API.

    Requires ECOS_API_KEY to be set in settings (.env).
    """

    def __init__(self, timeout: int = _TIMEOUT) -> None:
        self.api_key = settings.ECOS_API_KEY
        if not self.api_key:
            raise ValueError(
                "ECOS_API_KEY is not set. "
                "Add it to .env."
            )

        self.timeout = timeout
        self._session = requests.Session()
        self._kst = ZoneInfo("Asia/Seoul")

    def fetch_series(
        self,
        stat_code: str,
        item_code: str,
        period: str = "D",
        days: int = 365,
    ) -> BOKSeriesData:
        """
        Fetch the last `days` days of observations for
        (stat_code, item_code, period).

        Returns:
            BOKSeriesData with observations deduplicated by observation_date,
            in ascending date order.

        Raises:
            ValueError: If the ECOS API responds with an error code.
        """
        today = datetime.now(self._kst).date()
        start_date = today - timedelta(days=days)

        start_str = start_date.strftime("%Y%m%d")
        end_str = today.strftime("%Y%m%d")

        rows = self._fetch_all_rows(stat_code, item_code, period, start_str, end_str)
        fetched_at = datetime.utcnow().isoformat()

        observations: list[BOKSeriesObservation] = []
        seen_dates: set[str] = set()
        for row in rows:
            observation_date = self._format_date(row["TIME"])
            if observation_date in seen_dates:
                continue
            seen_dates.add(observation_date)
            observations.append(
                BOKSeriesObservation(
                    observation_date=observation_date,
                    value=float(row["DATA_VALUE"]),
                )
            )
        observations.sort(key=lambda obs: obs.observation_date)

        return BOKSeriesData(
            source="bok",
            stat_code=stat_code,
            item_code=item_code,
            observations=observations,
            fetched_at=fetched_at,
        )

    def fetch_last_1y_series(self, stat_code: str, item_code: str, period: str = "D") -> BOKSeriesData:
        """Fetch the last 365 days of observations."""
        return self.fetch_series(stat_code, item_code, period, days=365)

    # ------------------------------------------------------------------ #
    # Private helpers                                                      #
    # ------------------------------------------------------------------ #

    def _fetch_all_rows(
        self, stat_code: str, item_code: str, period: str, start_date: str, end_date: str
    ) -> list[dict]:
        first_page = self._fetch_page(stat_code, item_code, period, 1, _PAGE_SIZE, start_date, end_date)
        list_total_count = int(first_page.get("list_total_count", 0))
        rows = list(first_page.get("row", []))

        page_count = (list_total_count // _PAGE_SIZE) + 1
        for page in range(1, page_count):
            start = page * _PAGE_SIZE + 1
            end = (page + 1) * _PAGE_SIZE
            result = self._fetch_page(stat_code, item_code, period, start, end, start_date, end_date)
            rows.extend(result.get("row", []))

        return rows

    def _fetch_page(
        self, stat_code: str, item_code: str, period: str, start: int, end: int, start_date: str, end_date: str
    ) -> dict:
        url = (
            f"{_ECOS_BASE_URL}/{self.api_key}/json/kr/{start}/{end}/"
            f"{stat_code}/{period}/{start_date}/{end_date}/{item_code}"
        )

        response = self._session.get(url, timeout=self.timeout)
        response.raise_for_status()
        result = response.json()

        if "RESULT" in result:
            error = result["RESULT"]
            raise ValueError(
                f"ECOS StatisticSearch call failed: "
                f"{error.get('CODE')} - {error.get('MESSAGE')}"
            )

        return result.get("StatisticSearch", {})

    @staticmethod
    def _format_date(value: str) -> str:
        """ECOS TIME (YYYYMMDD) -> YYYY-MM-DD."""
        return f"{value[:4]}-{value[4:6]}-{value[6:]}"
