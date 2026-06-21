"""
app/scrapers/exchange_rate/kb_exchange_rate_scraper.py

KB Bank HTML-based USD/KRW exchange rate scraper.

Two query modes against the KB quics component endpoint:
  - 조회기준=1 (intraday): parse summary tables (#summary1, #summary3)
  - 조회기준=2 (range):    parse daily base-rate rows (등록일 / 매매 기준율)
"""
import logging
import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Optional
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup

from app.schemas.exchange_rate import (
    KBUsdKrwIntradaySummary,
    DailyQuote,
    KBUsdKrwDailySeries,
)
from app.scrapers.exchange_rate.base import BaseExchangeRateScraper

logger = logging.getLogger(__name__)

_KST = ZoneInfo("Asia/Seoul")

_QUERY_URL = (
    "https://obank.kbstar.com/quics"
    "?chgCompId=b103362&baseCompId=b103362&page=C101422&cc=b103362:b103362"
)
_TIMEOUT = 20

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/145.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
    "Origin": "https://obank.kbstar.com",
    "Referer": "https://obank.kbstar.com/quics?page=C101422",
    "Content-Type": "application/x-www-form-urlencoded",
}


class KBExchangeRateScraper(BaseExchangeRateScraper):
    """
    Scrapes USD/KRW data from KB Bank.

    Usage::

        scraper = KBExchangeRateScraper()
        summary = scraper.fetch_usdkrw_summary(search_date="20260612")
        series = scraper.fetch_usdkrw_range("20250614", "20260614")
    """

    def __init__(self, timeout: int = _TIMEOUT) -> None:
        self._session = requests.Session()
        self._session.headers.update(_HEADERS)
        self._timeout = timeout

    # ------------------------------------------------------------------
    # Public — intraday summary (조회기준=1)
    # ------------------------------------------------------------------

    def fetch_usdkrw_summary(
        self, search_date: Optional[str] = None
    ) -> KBUsdKrwIntradaySummary:
        """
        Fetch the intraday summary (first/last round, daily low/high/avg).

        Args:
            search_date: YYYYMMDD. Defaults to today.

        Raises:
            requests.HTTPError: Non-2xx response.
            ValueError:         Response missing expected summary tables.
        """
        if search_date is None:
            search_date = date.today().strftime("%Y%m%d")

        html = self._post_query(search_date)
        summary = self._parse_summary(html)
        logger.info("Extracted intraday summary for %s.", _format_date(search_date))
        return KBUsdKrwIntradaySummary(
            base_ccy="USD",
            quote_ccy="KRW",
            target_date=_format_date(search_date),
            observed_at=datetime.now(_KST),   # valid time (tz-aware)
            **summary,
        )

    # ------------------------------------------------------------------
    # Public — daily range series (조회기준=2)
    # ------------------------------------------------------------------

    def fetch_usdkrw_range(
        self,
        start_date: str,
        end_date: Optional[str] = None,
    ) -> KBUsdKrwDailySeries:
        """
        Fetch daily USD/KRW base rates over a date range.

        Args:
            start_date: YYYYMMDD.
            end_date:   YYYYMMDD. Defaults to today.

        Raises:
            requests.HTTPError: Non-2xx response.
            ValueError:         Response missing expected daily table.
        """
        if end_date is None:
            end_date = date.today().strftime("%Y%m%d")

        html = self._post_range_query(start_date, end_date)
        quotes = self._parse_daily_quotes(html)
        logger.info(
            "Extracted %d daily quotes for %s ~ %s.",
            len(quotes), start_date, end_date,
        )
        return KBUsdKrwDailySeries(
            base_ccy="USD",
            quote_ccy="KRW",
            start_date=_format_date(start_date),
            end_date=_format_date(end_date),
            observed_at=datetime.now(_KST),
            quotes=quotes,
        )

    # ------------------------------------------------------------------
    # Private — fetch
    # ------------------------------------------------------------------

    def _post_query(self, search_date: str) -> str:
        logger.info("POSTing KB intraday query for date=%s.", search_date)
        return self._post(_build_payload(search_date))

    def _post_range_query(self, start_date: str, end_date: str) -> str:
        logger.info("POSTing KB range query for %s ~ %s.", start_date, end_date)
        return self._post(_build_range_payload(start_date, end_date))

    def _post(self, payload: dict) -> str:
        resp = self._session.post(_QUERY_URL, data=payload, timeout=self._timeout)
        resp.raise_for_status()
        html = resp.text
        if not html or "targetTable" not in html:
            raise ValueError("KB query response does not contain targetTable.")
        return html

    # ------------------------------------------------------------------
    # Private — parsing
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_summary(html: str) -> dict:
        """Parse #summary1 / #summary3 cells into summary fields by header label."""
        soup = BeautifulSoup(html, "html.parser")
        fields = {
            "first_rate": _summary_cell(soup, "summary1", "최초회차"),
            "last_rate": _summary_cell(soup, "summary1", "최종회차"),
            "daily_low": _summary_cell(soup, "summary3", "일최저"),
            "daily_high": _summary_cell(soup, "summary3", "일최고"),
            "daily_avg": _summary_cell(soup, "summary3", "일평균"),
        }
        parsed = {}
        for name, raw in fields.items():
            value = _to_decimal(raw)
            if value is None:
                raise ValueError(f"Failed to parse summary field {name!r}: {raw!r}")
            parsed[name] = value
        return parsed

    @staticmethod
    def _parse_daily_quotes(html: str) -> list[DailyQuote]:
        """Parse daily rows (등록일 / 매매 기준율) from the range response."""
        soup = BeautifulSoup(html, "html.parser")
        detail_table = _find_daily_detail_table(soup)

        rows = detail_table.select("tbody tr") or detail_table.select("tr")
        quotes: list[DailyQuote] = []

        for row in rows:
            cells = row.select("td")
            if len(cells) < 2:
                continue
            quote_date = cells[0].get_text(" ", strip=True)
            base_rate = _to_decimal(cells[1].get_text(" ", strip=True))
            if not re.match(r"^\d{4}\.\d{2}\.\d{2}$", quote_date) or base_rate is None:
                continue
            quotes.append(DailyQuote(quote_date=quote_date, base_rate=base_rate))

        if not quotes:
            raise ValueError("No daily quote rows parsed from KB range response.")

        return quotes


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------


def _build_payload(search_date: str) -> dict:
    now = datetime.now()
    return {
        "btnClick": "", "DocType": "1", "통화코드": "", "조회년월일": "",
        "SiteName": "", "strFocusBtn": "",
        "고시회차기준": "1", "고시종류기준": "0",
        "조회기준": "1", "요청페이지": "1",
        "selDate1": "", "selDate2": "",
        "monyCd": "USD", "selDate": search_date,
        "고시통화명": "미국 달러",
        "기준일자": now.strftime("%Y.%m.%d"),
        "기준일시": now.strftime("%H:%M:%S"),
        "SEL_통화구분": "USD", "조회일자구분": "1",
        "searchDate": search_date,
        "startDate": search_date, "endDate": search_date,
        "고시회차선택": "1", "고시종류선택": "0",
    }


def _build_range_payload(start_date: str, end_date: str) -> dict:
    now = datetime.now()
    return {
        "btnClick": "", "DocType": "1", "통화코드": "", "조회년월일": "",
        "SiteName": "", "strFocusBtn": "",
        "고시회차기준": "1", "고시종류기준": "0",
        "조회기준": "2", "요청페이지": "1",       # 기간 조회
        "selDate1": start_date, "selDate2": end_date,
        "monyCd": "USD", "selDate": end_date,
        "고시통화명": "미국 달러",
        "기준일자": now.strftime("%Y.%m.%d"),
        "기준일시": now.strftime("%H:%M:%S"),
        "SEL_통화구분": "USD", "조회일자구분": "2",  # 기간 조회
        "searchDate": end_date,
        "startDate": start_date, "endDate": end_date,
        "고시회차선택": "1", "고시종류선택": "0",
    }


def _summary_cell(soup: BeautifulSoup, table_id: str, label: str) -> str:
    """Return the <td> value under the <th> matching `label` in #table_id."""
    table = soup.select_one(f"#{table_id}")
    if not table:
        raise ValueError(f"Could not find #{table_id} in KB response HTML.")

    headers = [th.get_text(" ", strip=True) for th in table.select("thead th")]
    try:
        idx = headers.index(label)
    except ValueError:
        raise ValueError(
            f"Label {label!r} not found in #{table_id} headers: {headers}"
        )

    row = table.select_one("tbody tr")
    if not row:
        raise ValueError(f"#{table_id} has no data row.")

    cells = row.select("td")
    if idx >= len(cells):
        raise ValueError(
            f"#{table_id}: header {label!r} at index {idx} but row has "
            f"{len(cells)} cells."
        )
    return cells[idx].get_text(" ", strip=True)


def _find_daily_detail_table(soup: BeautifulSoup):
    target = soup.select_one("#targetTable")
    if not target:
        raise ValueError("Could not find #targetTable in KB response HTML.")

    for table in target.select("table"):
        text = table.get_text(" ", strip=True)
        if "등록일" in text and "매매 기준율" in text:
            return table

    tables = target.select("table")
    if len(tables) >= 4:
        return tables[3]

    raise ValueError("Could not find daily detail table inside #targetTable.")


def _format_date(yyyymmdd: str) -> str:
    """Convert 'YYYYMMDD' to 'YYYY.MM.DD'."""
    if len(yyyymmdd) != 8 or not yyyymmdd.isdigit():
        raise ValueError(f"Invalid date format: {yyyymmdd!r}")
    return f"{yyyymmdd[:4]}.{yyyymmdd[4:6]}.{yyyymmdd[6:]}"


def _to_decimal(value: str) -> Optional[Decimal]:
    """Parse a numeric string into Decimal, stripping commas and whitespace."""
    text = str(value).strip().replace(",", "")
    if not text:
        return None
    match = re.search(r"[-+]?\d+(?:\.\d+)?", text)
    if not match:
        return None
    try:
        return Decimal(match.group(0))
    except (InvalidOperation, ValueError):
        return None