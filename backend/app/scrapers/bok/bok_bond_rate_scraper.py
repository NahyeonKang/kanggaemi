"""
app/scrapers/bok/bok_bond_rate_scraper.py

Scraper for the Bank of Korea (BOK) ECOS StatisticSearch API: historical
Korean treasury bond rates.
"""
import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import requests

from app.core.config import settings
from app.schemas.bok_bond_rate import BOKBondRateData, BOKBondRateItem

logger = logging.getLogger(__name__)

_ECOS_BASE_URL = "https://ecos.bok.or.kr/api/StatisticSearch"
_TIMEOUT = 20
_PAGE_SIZE = 100

_STAT_CODE_TREASURY_10Y = "817Y002"
ITEM_CODE_TREASURY_10Y = "010210000"
_PERIOD = "D"


class BOKBondRateScraper:
    """
    Fetches historical Korean treasury bond rates from the BOK ECOS
    StatisticSearch API.

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

    def fetch_last_1y_treasury_10y(self) -> BOKBondRateData:
        """
        Fetch the last 1 year of daily observations for the 10-year
        Korean treasury bond rate (item code 010210000).

        Returns:
            BOKBondRateData with items deduplicated by observation_date.

        Raises:
            ValueError: If the ECOS API responds with an error code.
        """
        today = datetime.now(self._kst).date()
        start_date = today - timedelta(days=365)

        start_str = start_date.strftime("%Y%m%d")
        end_str = today.strftime("%Y%m%d")

        rows = self._fetch_all_rows(start_str, end_str)
        fetched_at = datetime.utcnow().isoformat()

        items: list[BOKBondRateItem] = []
        seen_dates: set[str] = set()
        for row in rows:
            observation_date = self._format_date(row["TIME"])
            if observation_date in seen_dates:
                continue
            seen_dates.add(observation_date)
            items.append(
                BOKBondRateItem(
                    item_name=row["ITEM_NAME1"],
                    observation_date=observation_date,
                    value=float(row["DATA_VALUE"]),
                )
            )

        return BOKBondRateData(
            source="bok",
            item_code=ITEM_CODE_TREASURY_10Y,
            items=items,
            fetched_at=fetched_at,
        )

    # ------------------------------------------------------------------ #
    # Private helpers                                                      #
    # ------------------------------------------------------------------ #

    def _fetch_all_rows(self, start_date: str, end_date: str) -> list[dict]:
        first_page = self._fetch_page(1, _PAGE_SIZE, start_date, end_date)
        list_total_count = int(first_page.get("list_total_count", 0))
        rows = list(first_page.get("row", []))

        page_count = (list_total_count // _PAGE_SIZE) + 1
        for page in range(1, page_count):
            start = page * _PAGE_SIZE + 1
            end = (page + 1) * _PAGE_SIZE
            result = self._fetch_page(start, end, start_date, end_date)
            rows.extend(result.get("row", []))

        return rows

    def _fetch_page(self, start: int, end: int, start_date: str, end_date: str) -> dict:
        url = (
            f"{_ECOS_BASE_URL}/{self.api_key}/json/kr/{start}/{end}/"
            f"{_STAT_CODE_TREASURY_10Y}/{_PERIOD}/{start_date}/{end_date}/"
            f"{ITEM_CODE_TREASURY_10Y}"
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
