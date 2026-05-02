"""
app/scrapers/exchange_rate/kb_exchange_rate_scraper.py

KB Bank HTML-based USD/KRW exchange rate scraper.

POSTs to the KB Bank quics component endpoint and parses intraday
quote data from the returned HTML fragment.

Response structure:
  #targetTable — parent container; contains the detail table
  Detail table  — rows with 등록시간 and 매매 기준율 columns
"""
import logging
import re
from datetime import date, datetime, timedelta
from typing import Optional

import requests
from bs4 import BeautifulSoup

from app.schemas.exchange_rate import IntradayQuote, KBUsdKrwExchangeRate
from app.scrapers.exchange_rate.base import BaseExchangeRateScraper

logger = logging.getLogger(__name__)

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
    Scrapes intraday USD/KRW quotes from KB Bank by POSTing to the
    quics component endpoint.

    Usage::

        scraper = KBExchangeRateScraper()

        # fetch today's data
        result = scraper.fetch_usdkrw()

        # fetch data for a specific date
        result = scraper.fetch_usdkrw(search_date="20260305")

        print(result.target_date, len(result.quotes))
    """

    def __init__(self, timeout: int = _TIMEOUT) -> None:
        self._session = requests.Session()
        self._session.headers.update(_HEADERS)
        self._timeout = timeout

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def fetch_usdkrw(self, search_date: Optional[str] = None) -> KBUsdKrwExchangeRate:
        """
        Fetch intraday USD/KRW quotes for the given date.

        Args:
            search_date: Date string in YYYYMMDD format.
                         Defaults to today if not provided.

        Raises:
            requests.HTTPError: Non-2xx response.
            ValueError:         Response missing expected HTML structure.
        """
        if search_date is None:
            search_date = date.today().strftime("%Y%m%d")

        html = self._post_query(search_date)
        target_date = _format_date(search_date)
        fetched_at = datetime.now().isoformat()
        quotes = self._parse_quotes(html)
        logger.info("Extracted %d quotes for %s.", len(quotes), target_date)
        return KBUsdKrwExchangeRate(
            target_date=target_date,
            fetched_at=fetched_at,
            quotes=quotes,
        )

    # ------------------------------------------------------------------
    # Private — fetch
    # ------------------------------------------------------------------

    def _post_query(self, search_date: str) -> str:
        logger.info("POSTing KB query for date=%s.", search_date)
        resp = self._session.post(
            _QUERY_URL,
            data=_build_payload(search_date),
            timeout=self._timeout,
        )
        resp.raise_for_status()
        html = resp.text
        if not html or "targetTable" not in html:
            raise ValueError("KB query response does not contain targetTable.")
        return html

    # ------------------------------------------------------------------
    # Private — parsing
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_quotes(html: str) -> list[IntradayQuote]:
        """
        Parse intraday quotes from the KB HTML response.

        Raises:
            ValueError: #targetTable missing or no quote rows found.
        """
        soup = BeautifulSoup(html, "html.parser")
        detail_table = _find_detail_table(soup)

        rows = detail_table.select("tbody tr") or detail_table.select("tr")
        quotes: list[IntradayQuote] = []

        for row in rows:
            cells = row.select("td")
            if len(cells) < 3:
                continue
            quote_time = cells[1].get_text(" ", strip=True)
            base_rate = _to_float(cells[2].get_text(" ", strip=True))
            if not quote_time or base_rate is None:
                continue
            if not re.match(r"^\d{2}:\d{2}:\d{2}$", quote_time):
                continue
            quotes.append(IntradayQuote(quote_time=quote_time, base_rate=base_rate))

        if not quotes:
            raise ValueError("No quote rows parsed from KB response.")

        return quotes


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------


def _build_payload(search_date: str) -> dict:
    now = datetime.now()
    today = now.strftime("%Y%m%d")
    start_date = (now.date() - timedelta(days=7)).strftime("%Y%m%d")
    return {
        "btnClick": "",
        "DocType": "1",
        "통화코드": "",
        "조회년월일": "",
        "SiteName": "",
        "strFocusBtn": "",
        "고시회차기준": "1",
        "고시종류기준": "0",
        "조회기준": "1",
        "요청페이지": "1",
        "selDate1": "",
        "selDate2": "",
        "monyCd": "USD",
        "selDate": search_date,
        "고시통화명": "미국 달러",
        "기준일자": now.strftime("%Y.%m.%d"),
        "기준일시": now.strftime("%H:%M:%S"),
        "SEL_통화구분": "USD",
        "조회일자구분": "1",
        "searchDate": search_date,
        "startDate": start_date,  # 7 days before today
        "endDate": today,
        "고시회차선택": "1",
        "고시종류선택": "0",
    }


def _find_detail_table(soup: BeautifulSoup):
    target = soup.select_one("#targetTable")
    if not target:
        raise ValueError("Could not find #targetTable in KB response HTML.")

    tables = target.select("table")
    for table in tables:
        text = table.get_text(" ", strip=True)
        if "등록시간" in text and "매매 기준율" in text:
            return table

    if len(tables) >= 4:
        return tables[3]

    raise ValueError("Could not find intraday detail table inside #targetTable.")


def _format_date(search_date: str) -> str:
    """Convert 'YYYYMMDD' to 'YYYY.MM.DD'."""
    if len(search_date) != 8 or not search_date.isdigit():
        raise ValueError(f"Invalid search_date format: {search_date!r}")
    return f"{search_date[:4]}.{search_date[4:6]}.{search_date[6:]}"


def _to_float(value: str) -> Optional[float]:
    """Parse a numeric string, stripping commas and whitespace."""
    text = str(value).strip().replace(",", "")
    if not text:
        return None
    match = re.search(r"[-+]?\d+(?:\.\d+)?", text)
    if not match:
        return None
    try:
        return float(match.group(0))
    except ValueError:
        return None
