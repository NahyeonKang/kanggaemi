"""
app/scrapers/bok/bok_scraper.py

Generic BOK ECOS StatisticSearch scraper. yield 도메인의 KR daily 금리
(817Y002 / D / item_code) 등에 사용.
"""
import logging
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Optional
from zoneinfo import ZoneInfo

import requests

from app.core.config import settings
from app.schemas.yield_rate import BOKSeriesData, BOKSeriesObservation

logger = logging.getLogger(__name__)

_ECOS_BASE_URL = "https://ecos.bok.or.kr/api/StatisticSearch"
_TIMEOUT = 20
_PAGE_SIZE = 100


def _to_decimal(raw: object) -> Optional[Decimal]:
    if raw is None or str(raw).strip() == "":
        return None
    try:
        return Decimal(str(raw).strip())
    except (InvalidOperation, ValueError):
        return None


class BOKScraper:
    """Fetches statistical series from the BOK ECOS API. Requires ECOS_API_KEY."""

    def __init__(self, timeout: int = _TIMEOUT) -> None:
        self.api_key = settings.ECOS_API_KEY
        if not self.api_key:
            raise ValueError("ECOS_API_KEY is not set. Add it to .env.")

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
        """Fetch last `days` of observations. Dedup by date, ascending."""
        today = datetime.now(self._kst).date()
        start_date = today - timedelta(days=days)

        rows = self._fetch_all_rows(
            stat_code, item_code, period,
            start_date.strftime("%Y%m%d"), today.strftime("%Y%m%d"),
        )

        observations: list[BOKSeriesObservation] = []
        seen: set[str] = set()
        for row in rows:
            observation_date = self._format_date(row["TIME"], period)
            if observation_date in seen:
                continue
            seen.add(observation_date)
            observations.append(
                BOKSeriesObservation(
                    observation_date=observation_date,
                    value=_to_decimal(row.get("DATA_VALUE")),
                )
            )
        observations.sort(key=lambda obs: obs.observation_date)

        return BOKSeriesData(
            source="bok",
            stat_code=stat_code,
            item_code=item_code,
            resolution=period,
            observed_at=datetime.now(self._kst),
            observations=observations,
        )

    def fetch_last_1y_series(
        self, stat_code: str, item_code: str, period: str = "D"
    ) -> BOKSeriesData:
        return self.fetch_series(stat_code, item_code, period, days=365)

    # ── private ──────────────────────────────────────────────
    def _fetch_all_rows(
        self, stat_code, item_code, period, start_date, end_date
    ) -> list[dict]:
        first = self._fetch_page(stat_code, item_code, period, 1, _PAGE_SIZE, start_date, end_date)
        total = int(first.get("list_total_count", 0))
        rows = list(first.get("row", []))

        page_count = (total // _PAGE_SIZE) + 1
        for page in range(1, page_count):
            start = page * _PAGE_SIZE + 1
            end = (page + 1) * _PAGE_SIZE
            result = self._fetch_page(stat_code, item_code, period, start, end, start_date, end_date)
            rows.extend(result.get("row", []))
        return rows

    def _fetch_page(
        self, stat_code, item_code, period, start, end, start_date, end_date
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
                f"ECOS StatisticSearch call failed: {error.get('CODE')} - {error.get('MESSAGE')}"
            )
        return result.get("StatisticSearch", {})

    @staticmethod
    def _format_date(value: str, period: str = "D") -> str:
        """ECOS TIME → 'YYYY-MM-DD'. D: YYYYMMDD, M: YYYYMM(→ -01)."""
        if period == "M" and len(value) == 6:
            return f"{value[:4]}-{value[4:6]}-01"
        return f"{value[:4]}-{value[4:6]}-{value[6:]}"