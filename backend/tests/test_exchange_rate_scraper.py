import pytest
import requests

from app.scrapers.exchange_rate_scraper import (
    ExchangeRateResult,
    YahooExchangeRateScraper,
    _date_to_timestamp,
)

# ---------------------------------------------------------------------------
# Shared response fixtures
# ---------------------------------------------------------------------------

VALID_RESPONSE = {
    "amount": 1.0,
    "base": "USD",
    "date": "2024-01-15",
    "rates": {"KRW": 1325.67},
}

MISSING_KRW_RESPONSE = {
    "amount": 1.0,
    "base": "USD",
    "date": "2024-01-15",
    "rates": {"JPY": 148.0},
}

MALFORMED_RESPONSE = {"unexpected": "structure"}


# ---------------------------------------------------------------------------
# _parse: pure unit tests — no HTTP involved
# ---------------------------------------------------------------------------


class TestParse:
    def test_valid_response_returns_result(self):
        result = YahooExchangeRateScraper._parse(VALID_RESPONSE)
        assert isinstance(result, ExchangeRateResult)

    def test_symbol_is_usdkrw(self):
        result = YahooExchangeRateScraper._parse(VALID_RESPONSE)
        assert result.symbol == "USD/KRW"

    def test_price_parsed_correctly(self):
        result = YahooExchangeRateScraper._parse(VALID_RESPONSE)
        assert result.price == 1325.67

    def test_price_is_float(self):
        result = YahooExchangeRateScraper._parse(VALID_RESPONSE)
        assert isinstance(result.price, float)

    def test_bid_is_always_none(self):
        result = YahooExchangeRateScraper._parse(VALID_RESPONSE)
        assert result.bid is None

    def test_ask_is_always_none(self):
        result = YahooExchangeRateScraper._parse(VALID_RESPONSE)
        assert result.ask is None

    def test_timestamp_is_int(self):
        result = YahooExchangeRateScraper._parse(VALID_RESPONSE)
        assert isinstance(result.timestamp, int)

    def test_timestamp_is_positive(self):
        result = YahooExchangeRateScraper._parse(VALID_RESPONSE)
        assert result.timestamp > 0

    def test_missing_krw_raises_value_error(self):
        with pytest.raises(ValueError, match="KRW"):
            YahooExchangeRateScraper._parse(MISSING_KRW_RESPONSE)

    def test_malformed_response_raises_value_error(self):
        with pytest.raises(ValueError, match="Unexpected"):
            YahooExchangeRateScraper._parse(MALFORMED_RESPONSE)

    def test_none_response_raises_value_error(self):
        with pytest.raises(ValueError, match="Unexpected"):
            YahooExchangeRateScraper._parse(None)


# ---------------------------------------------------------------------------
# fetch_usdkrw_rate: monkeypatched HTTP tests
# ---------------------------------------------------------------------------


class TestFetchUsdKrwRate:
    def test_returns_exchange_rate_result(self, monkeypatch):
        monkeypatch.setattr(
            "app.scrapers.exchange_rate_scraper.requests.get",
            _mock_get(VALID_RESPONSE),
        )
        result = YahooExchangeRateScraper().fetch_usdkrw_rate()
        assert isinstance(result, ExchangeRateResult)

    def test_correct_price_returned(self, monkeypatch):
        monkeypatch.setattr(
            "app.scrapers.exchange_rate_scraper.requests.get",
            _mock_get(VALID_RESPONSE),
        )
        result = YahooExchangeRateScraper().fetch_usdkrw_rate()
        assert result.price == 1325.67

    def test_correct_symbol_returned(self, monkeypatch):
        monkeypatch.setattr(
            "app.scrapers.exchange_rate_scraper.requests.get",
            _mock_get(VALID_RESPONSE),
        )
        result = YahooExchangeRateScraper().fetch_usdkrw_rate()
        assert result.symbol == "USD/KRW"

    def test_http_error_propagates(self, monkeypatch):
        monkeypatch.setattr(
            "app.scrapers.exchange_rate_scraper.requests.get",
            _mock_get_http_error(403),
        )
        with pytest.raises(requests.HTTPError):
            YahooExchangeRateScraper().fetch_usdkrw_rate()

    def test_missing_krw_raises_value_error(self, monkeypatch):
        monkeypatch.setattr(
            "app.scrapers.exchange_rate_scraper.requests.get",
            _mock_get(MISSING_KRW_RESPONSE),
        )
        with pytest.raises(ValueError, match="KRW"):
            YahooExchangeRateScraper().fetch_usdkrw_rate()

    def test_bid_ask_always_none(self, monkeypatch):
        monkeypatch.setattr(
            "app.scrapers.exchange_rate_scraper.requests.get",
            _mock_get(VALID_RESPONSE),
        )
        result = YahooExchangeRateScraper().fetch_usdkrw_rate()
        assert result.bid is None
        assert result.ask is None


# ---------------------------------------------------------------------------
# _date_to_timestamp helper
# ---------------------------------------------------------------------------


class TestDateToTimestamp:
    def test_returns_int(self):
        assert isinstance(_date_to_timestamp("2024-01-15"), int)

    def test_positive_value(self):
        assert _date_to_timestamp("2024-01-15") > 0

    def test_invalid_format_raises(self):
        with pytest.raises(ValueError):
            _date_to_timestamp("15-01-2024")

    def test_none_raises(self):
        with pytest.raises(ValueError):
            _date_to_timestamp(None)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _FakeResponse:
    def __init__(self, status_code: int, payload: dict):
        self.status_code = status_code
        self._payload = payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}", response=self)

    def json(self):
        return self._payload


def _mock_get(payload: dict):
    def _get(*args, **kwargs):
        return _FakeResponse(200, payload)
    return _get


def _mock_get_http_error(status_code: int):
    def _get(*args, **kwargs):
        resp = _FakeResponse(status_code, {})
        resp.raise_for_status()
    return _get
