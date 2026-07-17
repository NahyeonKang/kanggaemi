"""
app/scrapers/kis/kis_chart_scraper.py

KIS 기간별 시세(일/주/월/년) 통합 스크래퍼 — 시세 도메인.

  - stock  [016] FHKST03010100 inquire-daily-itemchartprice   (stck_*)
  - index  [021] FHKUP03500100 inquire-daily-indexchartprice  (bstp_nmix_*)
  - future [008] FHKIF03020100 inquire-daily-fuopchartprice   (futs_*)
  - option [008] FHKIF03020100 (futs_*, market_div O)

output2가 셋 다 같은 shape(날짜+OHLC+거래량+대금)라 필드맵으로 통합.
output1은 자산군별로 다르게 파싱(주식=valuation, 선물옵션=derivative, 업종=생략).
"""
import logging
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Optional
from zoneinfo import ZoneInfo

from app.schemas.instrument_price import (
    OhlcvObservation, StockValuationSnapshot, DerivativeSnapshot, ChartResult,
)
from app.scrapers.kis.kis_auth import KISAuthClient, smart_sleep

logger = logging.getLogger(__name__)

_KST = ZoneInfo("Asia/Seoul")
_MAX_PAGES = 10

# 자산군별 요청 설정
_CHART_CONFIG = {
    "stock": {
        "url": "/uapi/domestic-stock/v1/quotations/inquire-daily-itemchartprice",
        "tr_id": "FHKST03010100", "market_div": "J", "paginate": False,
    },
    "index": {
        "url": "/uapi/domestic-stock/v1/quotations/inquire-daily-indexchartprice",
        "tr_id": "FHKUP03500100", "market_div": "U", "paginate": True,
    },
    "future": {
        "url": "/uapi/domestic-futureoption/v1/quotations/inquire-daily-fuopchartprice",
        "tr_id": "FHKIF03020100", "market_div": "F", "paginate": True,
    },
    "option": {
        "url": "/uapi/domestic-futureoption/v1/quotations/inquire-daily-fuopchartprice",
        "tr_id": "FHKIF03020100", "market_div": "O", "paginate": True,
    },
}

# 자산군별 output2 OHLCV 필드맵 (date는 공통 stck_bsop_date)
_OHLCV_MAP = {
    "stock": {"open": "stck_oprc", "high": "stck_hgpr", "low": "stck_lwpr",
              "close": "stck_clpr", "volume": "acml_vol", "amount": "acml_tr_pbmn"},
    "index": {"open": "bstp_nmix_oprc", "high": "bstp_nmix_hgpr", "low": "bstp_nmix_lwpr",
              "close": "bstp_nmix_prpr", "volume": "acml_vol", "amount": "acml_tr_pbmn"},
    "future": {"open": "futs_oprc", "high": "futs_hgpr", "low": "futs_lwpr",
               "close": "futs_prpr", "volume": "acml_vol", "amount": "acml_tr_pbmn"},
}
_OHLCV_MAP["option"] = _OHLCV_MAP["future"]


class KISChartScraper:
    """Fetches period OHLCV + per-asset-class snapshot from KIS."""

    def __init__(self, auth_client: Optional[KISAuthClient] = None) -> None:
        self._auth = auth_client or KISAuthClient()

    def fetch_period_chart(
        self,
        asset_class: str,                  # stock | index | future | option
        entity_code: str,
        period: str = "D",
        start_date: str = "",
        end_date: str = "",
        adj: str = "0",                    # 주식 전용(수정주가). 그 외 무시
        market_div: Optional[str] = None,
    ) -> ChartResult:
        cfg = _CHART_CONFIG[asset_class]
        params = {
            "FID_COND_MRKT_DIV_CODE": market_div or cfg["market_div"],
            "FID_INPUT_ISCD": entity_code,
            "FID_INPUT_DATE_1": start_date or "",
            "FID_INPUT_DATE_2": end_date or "",
            "FID_PERIOD_DIV_CODE": period,
        }
        if asset_class == "stock":
            params["FID_ORG_ADJ_PRC"] = adj

        output1 = None
        rows: list = []
        tr_cont = ""
        for page in range(_MAX_PAGES):
            res = self._auth.url_fetch(cfg["url"], cfg["tr_id"], tr_cont, params)
            if not res.isOK():
                res.printError(cfg["url"])
                raise ValueError(
                    f"KIS chart call failed ({asset_class}): "
                    f"{res.getErrorCode()} - {res.getErrorMessage()}"
                )
            body = res.getBody()
            if output1 is None:
                output1 = getattr(body, "output1", None)
            rows.extend(_as_list(getattr(body, "output2", None)))

            if not cfg["paginate"]:
                break
            tr_cont = res.getHeader().tr_cont
            if tr_cont not in ("M", "F"):
                break
            tr_cont = "N"
            smart_sleep()

        fmap = _OHLCV_MAP[asset_class]
        observations = [
            _parse_ohlcv(r, fmap) for r in rows if _get(r, "stck_bsop_date")
        ]

        valuation = _parse_valuation(output1) if asset_class == "stock" else None
        derivative = (
            _parse_derivative(output1) if asset_class in ("future", "option") else None
        )

        return ChartResult(
            source="kis",
            asset_class=asset_class,
            entity_code=entity_code,
            resolution=period,
            observed_at=datetime.now(_KST),
            observations=observations,
            valuation=valuation,
            derivative=derivative,
        )


# ── parsing ──────────────────────────────────────────────────
def _parse_ohlcv(row: object, fmap: dict) -> OhlcvObservation:
    return OhlcvObservation(
        observation_date=_fmt_date(str(_get(row, "stck_bsop_date"))),
        open=_to_decimal(_get(row, fmap["open"])),
        high=_to_decimal(_get(row, fmap["high"])),
        low=_to_decimal(_get(row, fmap["low"])),
        close=_to_decimal(_get(row, fmap["close"])),
        volume=_to_decimal(_get(row, fmap["volume"])),
        amount=_to_decimal(_get(row, fmap["amount"])),
    )


def _parse_valuation(o1: object) -> StockValuationSnapshot:
    if not o1:
        return StockValuationSnapshot()
    return StockValuationSnapshot(
        name=_get(o1, "hts_kor_isnm"),
        current_price=_to_decimal(_get(o1, "stck_prpr")),
        upper_limit=_to_decimal(_get(o1, "stck_mxpr")),
        lower_limit=_to_decimal(_get(o1, "stck_llam")),
        vol_turnover=_to_decimal(_get(o1, "vol_tnrt")),
        listed_shares=_to_decimal(_get(o1, "lstn_stcn")),
        market_cap=_to_decimal(_get(o1, "hts_avls")),
        per=_to_decimal(_get(o1, "per")),
        pbr=_to_decimal(_get(o1, "pbr")),
    )


def _parse_derivative(o1: object) -> DerivativeSnapshot:
    if not o1:
        return DerivativeSnapshot()
    return DerivativeSnapshot(
        name=_get(o1, "hts_kor_isnm"),
        current_price=_to_decimal(_get(o1, "futs_prpr")),
        upper_limit=_to_decimal(_get(o1, "futs_mxpr")),
        lower_limit=_to_decimal(_get(o1, "futs_llam")),
        basis=_to_decimal(_get(o1, "basis")),
        kospi200=_to_decimal(_get(o1, "kospi200_nmix")),
        open_interest=_to_decimal(_get(o1, "hts_otst_stpl_qty")),
        oi_change=_to_decimal(_get(o1, "otst_stpl_qty_icdc")),
        theoretical_price=_to_decimal(_get(o1, "hts_thpr")),
        disparity=_to_decimal(_get(o1, "dprt")),
        tick_strength=_to_decimal(_get(o1, "tday_rltv")),
    )


# ── helpers ──────────────────────────────────────────────────
def _get(obj: object, key: str):
    if isinstance(obj, dict):
        return obj.get(key)
    return getattr(obj, key, None)


def _as_list(raw: object) -> list:
    if not raw:
        return []
    return raw if isinstance(raw, list) else [raw]


def _fmt_date(yyyymmdd: str) -> str:
    if len(yyyymmdd) == 8 and yyyymmdd.isdigit():
        return f"{yyyymmdd[:4]}-{yyyymmdd[4:6]}-{yyyymmdd[6:]}"
    return yyyymmdd


def _to_decimal(value: object) -> Optional[Decimal]:
    if value is None or str(value).strip() == "":
        return None
    try:
        return Decimal(str(value).strip())
    except (InvalidOperation, ValueError):
        return None