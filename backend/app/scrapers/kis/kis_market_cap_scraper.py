"""
app/scrapers/kis/kis_market_cap_scraper.py

KIS 국내주식 시가총액 상위 [국내주식-091] 스크래퍼 — 유니버스 소스.
시장(market)을 fid_input_iscd로 구분. tr_cont M 연속조회. top_n 도달 시 조기 중단.
"""
import logging
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Optional
from zoneinfo import ZoneInfo

from app.schemas.market_cap_ranking import MarketCapRow, MarketCapRanking
from app.scrapers.kis.kis_auth import KISAuthClient, smart_sleep

logger = logging.getLogger(__name__)

_KST = ZoneInfo("Asia/Seoul")
_PATH = "/uapi/domestic-stock/v1/ranking/market-cap"
_TR_ID = "FHPST01740000"
_MAX_PAGES = 20

# market → fid_input_iscd
_MARKET_CODE = {
    "all": "0000",       # 전체
    "kospi": "0001",     # 거래소(코스피)
    "kosdaq": "1001",    # 코스닥
    "kospi200": "2001",  # 코스피200
}


class KISMarketCapScraper:
    """Fetches domestic market-cap ranking from KIS."""

    def __init__(self, auth_client: Optional[KISAuthClient] = None) -> None:
        self._auth = auth_client or KISAuthClient()

    def fetch_market_cap_ranking(
        self,
        market: str = "kospi",
        div_cls_code: str = "0",       # 0:전체 1:보통주 2:우선주
        top_n: Optional[int] = None,   # 상위 N만(도달 시 조기 중단). None=페이지 한도까지
    ) -> MarketCapRanking:
        if market not in _MARKET_CODE:
            raise ValueError(f"market must be one of {list(_MARKET_CODE)}, got: {market!r}")

        params = {
            "fid_cond_mrkt_div_code": "J",
            "fid_cond_scr_div_code": "20174",
            "fid_div_cls_code": div_cls_code,
            "fid_input_iscd": _MARKET_CODE[market],
            "fid_trgt_cls_code": "0",
            "fid_trgt_exls_cls_code": "0",
            "fid_input_price_1": "",
            "fid_input_price_2": "",
            "fid_vol_cnt": "",
        }

        rows: list[MarketCapRow] = []
        seen: set[str] = set()
        tr_cont = ""
        for _ in range(_MAX_PAGES):
            res = self._auth.url_fetch(_PATH, _TR_ID, tr_cont, params)
            if not res.isOK():
                res.printError(_PATH)
                raise ValueError(
                    f"KIS market-cap call failed ({market}): "
                    f"{res.getErrorCode()} - {res.getErrorMessage()}"
                )
            for raw in _as_list(getattr(res.getBody(), "output", None)):
                row = _parse_row(raw)
                if row is None or row.ticker in seen:
                    continue
                seen.add(row.ticker)
                rows.append(row)
            if top_n is not None and len(rows) >= top_n:
                rows = rows[:top_n]
                break
            tr_cont = res.getHeader().tr_cont
            if tr_cont not in ("M", "F"):
                break
            tr_cont = "N"
            smart_sleep()

        return MarketCapRanking(
            source="kis", market=market,
            observed_at=datetime.now(_KST), rows=rows,
        )


# ── parsing ──────────────────────────────────────────────────
def _parse_row(raw: object) -> Optional[MarketCapRow]:
    ticker = _get(raw, "mksc_shrn_iscd")
    rank = _to_int(_get(raw, "data_rank"))
    if not ticker or rank is None:
        return None
    return MarketCapRow(
        rank=rank,
        ticker=str(ticker).strip(),
        name=_get(raw, "hts_kor_isnm"),
        close_price=_to_decimal(_get(raw, "stck_prpr")),
        volume=_to_decimal(_get(raw, "acml_vol")),
        listed_shares=_to_decimal(_get(raw, "lstn_stcn")),
        market_cap=_to_decimal(_get(raw, "stck_avls")),
        market_weight=_to_decimal(_get(raw, "mrkt_whol_avls_rlim")),
    )


def _get(obj: object, key: str):
    if isinstance(obj, dict):
        return obj.get(key)
    return getattr(obj, key, None)


def _as_list(raw: object) -> list:
    if not raw:
        return []
    return raw if isinstance(raw, list) else [raw]


def _to_int(value: object) -> Optional[int]:
    s = str(value).strip() if value is not None else ""
    if not s:
        return None
    try:
        return int(s)
    except ValueError:
        return None


def _to_decimal(value: object) -> Optional[Decimal]:
    if value is None or str(value).strip() == "":
        return None
    try:
        return Decimal(str(value).strip())
    except (InvalidOperation, ValueError):
        return None