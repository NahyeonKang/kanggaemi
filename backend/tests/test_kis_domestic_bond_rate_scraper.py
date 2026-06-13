import pytest

from app.schemas.domestic_bond_rate import DomesticBondRateData, DomesticBondRateItem
from app.scrapers.kis.kis_domestic_bond_rate_scraper import (
    KISDomesticBondRateScraper,
    _parse_items,
)

# ---------------------------------------------------------------------------
# Shared response fixtures
# ---------------------------------------------------------------------------

OUTPUT1_ROW = {
    "bcdt_code": "001",
    "hts_kor_isnm": "국고채3년",
    "bond_mnrt_prpr": "3.250",
    "prdy_vrss_sign": "2",
    "bond_mnrt_prdy_vrss": "0.010",
    "prdy_ctrt": "0.31",
    "stck_bsop_date": "20260612",
}

OUTPUT2_ROWS = [
    {
        "bcdt_code": "002",
        "hts_kor_isnm": "국고채5년",
        "bond_mnrt_prpr": "3.310",
        "prdy_vrss_sign": "5",
        "bond_mnrt_prdy_vrss": "0.000",
        "bstp_nmix_prdy_ctrt": "0.00",
        "stck_bsop_date": "20260612",
    },
    {
        "bcdt_code": "003",
        "hts_kor_isnm": "국고채10년",
        "bond_mnrt_prpr": "3.420",
        "prdy_vrss_sign": "1",
        "bond_mnrt_prdy_vrss": "-0.020",
        "bstp_nmix_prdy_ctrt": "-0.58",
        "stck_bsop_date": "20260612",
    },
]


# ---------------------------------------------------------------------------
# _parse_items: pure unit tests — no HTTP involved
# ---------------------------------------------------------------------------


class TestParseItems:
    def test_none_returns_empty_list(self):
        assert _parse_items(None) == []

    def test_empty_dict_returns_empty_list(self):
        assert _parse_items({}) == []

    def test_single_dict_returns_one_item(self):
        items = _parse_items(OUTPUT1_ROW)
        assert len(items) == 1
        assert isinstance(items[0], DomesticBondRateItem)

    def test_list_returns_all_items(self):
        items = _parse_items(OUTPUT2_ROWS)
        assert len(items) == 2

    def test_fields_mapped_correctly(self):
        item = _parse_items(OUTPUT1_ROW)[0]
        assert item.bcdt_code == "001"
        assert item.hts_kor_isnm == "국고채3년"
        assert item.bond_mnrt_prpr == "3.250"
        assert item.prdy_vrss_sign == "2"
        assert item.bond_mnrt_prdy_vrss == "0.010"
        assert item.prdy_ctrt == "0.31"
        assert item.stck_bsop_date == "20260612"

    def test_missing_optional_fields_are_none(self):
        item = _parse_items(OUTPUT2_ROWS)[0]
        assert item.prdy_ctrt is None
        assert item.bstp_nmix_prdy_ctrt == "0.00"

    def test_missing_required_fields_default_to_empty_string(self):
        item = _parse_items({"hts_kor_isnm": "국고채3년"})[0]
        assert item.bcdt_code == ""
        assert item.bond_mnrt_prpr == ""
        assert item.stck_bsop_date == ""


# ---------------------------------------------------------------------------
# fetch_comp_interest: fake KISAuthClient tests
# ---------------------------------------------------------------------------


class TestFetchCompInterest:
    def test_returns_domestic_bond_rate_data(self):
        auth_client = _FakeAuthClient(
            [_fake_resp(output1=OUTPUT1_ROW, output2=OUTPUT2_ROWS)]
        )
        result = KISDomesticBondRateScraper(auth_client=auth_client).fetch_comp_interest(
            "I", "20702", "1", ""
        )
        assert isinstance(result, DomesticBondRateData)

    def test_output1_and_output2_parsed(self):
        auth_client = _FakeAuthClient(
            [_fake_resp(output1=OUTPUT1_ROW, output2=OUTPUT2_ROWS)]
        )
        result = KISDomesticBondRateScraper(auth_client=auth_client).fetch_comp_interest(
            "I", "20702", "1", ""
        )
        assert len(result.output1) == 1
        assert len(result.output2) == 2
        assert result.output1[0].hts_kor_isnm == "국고채3년"
        assert result.output2[1].hts_kor_isnm == "국고채10년"

    def test_request_params_and_metadata(self):
        auth_client = _FakeAuthClient([_fake_resp(output1=OUTPUT1_ROW)])
        result = KISDomesticBondRateScraper(auth_client=auth_client).fetch_comp_interest(
            "I", "20702", "1", ""
        )
        assert result.source == "kis"
        assert result.market_div_code == "I"
        assert result.screen_div_code == "20702"
        assert result.cls_code == "1"

        call = auth_client.calls[0]
        assert call["tr_id"] == "FHPST07020000"
        assert call["tr_cont"] == ""
        assert call["params"] == {
            "FID_COND_MRKT_DIV_CODE": "I",
            "FID_COND_SCR_DIV_CODE": "20702",
            "FID_DIV_CLS_CODE": "1",
            "FID_DIV_CLS_CODE1": "",
        }

    def test_fetched_at_is_iso_datetime(self):
        from datetime import datetime

        auth_client = _FakeAuthClient([_fake_resp(output1=OUTPUT1_ROW)])
        result = KISDomesticBondRateScraper(auth_client=auth_client).fetch_comp_interest(
            "I", "20702", "1", ""
        )
        datetime.fromisoformat(result.fetched_at)

    def test_follows_continuation_pages(self, monkeypatch):
        monkeypatch.setattr(
            "app.scrapers.kis.kis_domestic_bond_rate_scraper.smart_sleep",
            lambda *a, **k: None,
        )
        auth_client = _FakeAuthClient(
            [
                _fake_resp(output1=OUTPUT1_ROW, tr_cont="M"),
                _fake_resp(output2=OUTPUT2_ROWS, tr_cont=""),
            ]
        )
        result = KISDomesticBondRateScraper(auth_client=auth_client).fetch_comp_interest(
            "I", "20702", "1", ""
        )
        assert len(result.output1) == 1
        assert len(result.output2) == 2
        assert len(auth_client.calls) == 2
        assert auth_client.calls[0]["tr_cont"] == ""
        assert auth_client.calls[1]["tr_cont"] == "N"

    def test_stops_at_max_pages(self, monkeypatch):
        monkeypatch.setattr(
            "app.scrapers.kis.kis_domestic_bond_rate_scraper.smart_sleep",
            lambda *a, **k: None,
        )
        responses = [_fake_resp(output1=OUTPUT1_ROW, tr_cont="M") for _ in range(10)]
        auth_client = _FakeAuthClient(responses)
        result = KISDomesticBondRateScraper(auth_client=auth_client).fetch_comp_interest(
            "I", "20702", "1", ""
        )
        assert len(auth_client.calls) == 10
        assert len(result.output1) == 10

    def test_error_response_raises_value_error(self):
        auth_client = _FakeAuthClient(
            [_fake_resp(rt_cd="1", msg_cd="EGW00123", msg1="모의투자 미지원 종목입니다.")]
        )
        with pytest.raises(ValueError, match="EGW00123"):
            KISDomesticBondRateScraper(auth_client=auth_client).fetch_comp_interest(
                "I", "20702", "1", ""
            )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _FakeBody:
    def __init__(self, rt_cd, msg_cd, msg1, output1=None, output2=None):
        self.rt_cd = rt_cd
        self.msg_cd = msg_cd
        self.msg1 = msg1
        if output1 is not None:
            self.output1 = output1
        if output2 is not None:
            self.output2 = output2


class _FakeHeader:
    def __init__(self, tr_cont):
        self.tr_cont = tr_cont


class _FakeAPIResp:
    def __init__(self, rt_cd, msg_cd, msg1, output1, output2, tr_cont):
        self._body = _FakeBody(rt_cd, msg_cd, msg1, output1, output2)
        self._header = _FakeHeader(tr_cont)

    def isOK(self):
        return self._body.rt_cd == "0"

    def getBody(self):
        return self._body

    def getHeader(self):
        return self._header

    def getErrorCode(self):
        return self._body.msg_cd

    def getErrorMessage(self):
        return self._body.msg1

    def printError(self, url):
        pass


def _fake_resp(rt_cd="0", msg_cd="MCA00000", msg1="정상처리", output1=None, output2=None, tr_cont=""):
    return _FakeAPIResp(rt_cd, msg_cd, msg1, output1, output2, tr_cont)


class _FakeAuthClient:
    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = []

    def url_fetch(self, api_url, tr_id, tr_cont, params, post_flag=False):
        self.calls.append(
            {"api_url": api_url, "tr_id": tr_id, "tr_cont": tr_cont, "params": params}
        )
        return self._responses.pop(0)
