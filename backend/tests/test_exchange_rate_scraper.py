import pytest
import requests

from app.schemas.exchange_rate import IntradayQuote, KBUsdKrwExchangeRate
from app.scrapers.exchange_rate.kb_exchange_rate_scraper import (
    KBExchangeRateScraper,
    _build_payload,
    _find_detail_table,
    _format_date,
    _to_float,
)

# ---------------------------------------------------------------------------
# Shared response fixtures
# ---------------------------------------------------------------------------

VALID_HTML = """
<div id="targetTable">
  <table><tr><td>unrelated table</td></tr></table>
  <table>
    <thead>
      <tr><th>순번</th><th>등록시간</th><th>매매 기준율</th></tr>
    </thead>
    <tbody>
      <tr><td>1</td><td>09:00:00</td><td>1,325.50</td></tr>
      <tr><td>2</td><td>09:30:00</td><td>1,326.10</td></tr>
    </tbody>
  </table>
</div>
"""

NO_TARGET_TABLE_HTML = "<div>no target table here</div>"

EMPTY_ROWS_HTML = """
<div id="targetTable">
  <table>
    <thead>
      <tr><th>순번</th><th>등록시간</th><th>매매 기준율</th></tr>
    </thead>
    <tbody></tbody>
  </table>
</div>
"""


# ---------------------------------------------------------------------------
# _to_float: pure unit tests
# ---------------------------------------------------------------------------


class TestToFloat:
    def test_parses_comma_separated_number(self):
        assert _to_float("1,325.50") == 1325.50

    def test_parses_plain_number(self):
        assert _to_float("1326.1") == 1326.1

    def test_strips_whitespace(self):
        assert _to_float("  1,000.00  ") == 1000.0

    def test_empty_string_returns_none(self):
        assert _to_float("") is None

    def test_non_numeric_returns_none(self):
        assert _to_float("N/A") is None

    def test_negative_number(self):
        assert _to_float("-1.5") == -1.5


# ---------------------------------------------------------------------------
# _format_date: pure unit tests
# ---------------------------------------------------------------------------


class TestFormatDate:
    def test_formats_yyyymmdd(self):
        assert _format_date("20260305") == "2026.03.05"

    def test_invalid_length_raises_value_error(self):
        with pytest.raises(ValueError):
            _format_date("2026035")

    def test_non_digit_raises_value_error(self):
        with pytest.raises(ValueError):
            _format_date("2026-03-05")


# ---------------------------------------------------------------------------
# _build_payload: pure unit tests
# ---------------------------------------------------------------------------


class TestBuildPayload:
    def test_search_date_is_set(self):
        payload = _build_payload("20260305")
        assert payload["searchDate"] == "20260305"
        assert payload["selDate"] == "20260305"

    def test_currency_is_usd(self):
        payload = _build_payload("20260305")
        assert payload["monyCd"] == "USD"
        assert payload["SEL_통화구분"] == "USD"


# ---------------------------------------------------------------------------
# _find_detail_table / _parse_quotes: parsing tests
# ---------------------------------------------------------------------------


class TestParseQuotes:
    def test_parses_valid_html(self):
        quotes = KBExchangeRateScraper._parse_quotes(VALID_HTML)
        assert len(quotes) == 2
        assert all(isinstance(q, IntradayQuote) for q in quotes)

    def test_quote_fields_mapped_correctly(self):
        quotes = KBExchangeRateScraper._parse_quotes(VALID_HTML)
        assert quotes[0].quote_time == "09:00:00"
        assert quotes[0].base_rate == 1325.50
        assert quotes[1].quote_time == "09:30:00"
        assert quotes[1].base_rate == 1326.10

    def test_missing_target_table_raises_value_error(self):
        with pytest.raises(ValueError, match="targetTable"):
            KBExchangeRateScraper._parse_quotes(NO_TARGET_TABLE_HTML)

    def test_no_quote_rows_raises_value_error(self):
        with pytest.raises(ValueError, match="No quote rows"):
            KBExchangeRateScraper._parse_quotes(EMPTY_ROWS_HTML)


# ---------------------------------------------------------------------------
# fetch_usdkrw: monkeypatched HTTP tests
# ---------------------------------------------------------------------------


class TestFetchUsdKrw:
    def test_returns_kb_usdkrw_exchange_rate(self, monkeypatch):
        scraper = KBExchangeRateScraper()
        monkeypatch.setattr(scraper._session, "post", _mock_post(VALID_HTML))

        result = scraper.fetch_usdkrw(search_date="20260305")
        assert isinstance(result, KBUsdKrwExchangeRate)

    def test_target_date_formatted(self, monkeypatch):
        scraper = KBExchangeRateScraper()
        monkeypatch.setattr(scraper._session, "post", _mock_post(VALID_HTML))

        result = scraper.fetch_usdkrw(search_date="20260305")
        assert result.target_date == "2026.03.05"

    def test_quotes_parsed(self, monkeypatch):
        scraper = KBExchangeRateScraper()
        monkeypatch.setattr(scraper._session, "post", _mock_post(VALID_HTML))

        result = scraper.fetch_usdkrw(search_date="20260305")
        assert len(result.quotes) == 2
        assert result.quotes[0].base_rate == 1325.50

    def test_missing_target_table_raises_value_error(self, monkeypatch):
        scraper = KBExchangeRateScraper()
        monkeypatch.setattr(scraper._session, "post", _mock_post(NO_TARGET_TABLE_HTML))

        with pytest.raises(ValueError, match="targetTable"):
            scraper.fetch_usdkrw(search_date="20260305")

    def test_http_error_propagates(self, monkeypatch):
        scraper = KBExchangeRateScraper()
        monkeypatch.setattr(scraper._session, "post", _mock_post_http_error(500))

        with pytest.raises(requests.HTTPError):
            scraper.fetch_usdkrw(search_date="20260305")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _FakeResponse:
    def __init__(self, status_code: int, text: str):
        self.status_code = status_code
        self.text = text

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}", response=self)


def _mock_post(html: str):
    def _post(*args, **kwargs):
        return _FakeResponse(200, html)
    return _post


def _mock_post_http_error(status_code: int):
    def _post(*args, **kwargs):
        resp = _FakeResponse(status_code, "")
        resp.raise_for_status()
        return resp
    return _post
