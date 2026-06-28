"""
app/scrapers/kis/kis_program_scraper.py

KIS 프로그램매매 추이(일별) 스크래퍼 — 수급(flow) 도메인.
인증(KISAuthClient)만 공유, 도메인 분리.

  - 시장 [국내주식-115] FHPPG04600001 : comp-program-trade-daily, 페이징 없음.
  - 종목 [국내주식-113] FHPPG04650201 : program-trade-by-stock-daily, 페이징 없음.

필드명이 {trade_class}_{account_type}_{side}_{metric}로 규칙적이라
조합별로 필드명을 생성해 공통 파싱. 없는 필드는 None(부분 데이터 허용).
"""
import logging
from datetime import datetime
from decimal import Decimal, InvalidOperation
from itertools import product
from typing import Optional
from zoneinfo import ZoneInfo

from app.schemas.program_trade import ProgramTradeObservation, ProgramTradeSeries
from app.scrapers.kis.kis_auth import KISAuthClient

logger = logging.getLogger(__name__)

_KST = ZoneInfo("Asia/Seoul")

_MARKET_PATH = "/uapi/domestic-stock/v1/quotations/comp-program-trade-daily"
_MARKET_TR_ID = "FHPPG04600001"
_STOCK_PATH = "/uapi/domestic-stock/v1/quotations/program-trade-by-stock-daily"
_STOCK_TR_ID = "FHPPG04650201"

_MARKET_CLS = {"KOSPI": "K", "KOSDAQ": "Q"}

_TRADE_CLASSES = ("arbt", "nabt", "whol")        # 차익 / 비차익 / 전체
_ACCOUNT_TYPES = ("entm", "onsl", "smtn")        # 위탁 / 자기 / 합계
_MARKET_COMBOS = list(product(_TRADE_CLASSES, _ACCOUNT_TYPES))   # 9
_STOCK_COMBOS = [("whol", "smtn")]               # 종목은 전체 합계만


class KISProgramScraper:
    """Fetches program-trade trends (일별) from KIS."""

    def __init__(self, auth_client: Optional[KISAuthClient] = None) -> None:
        self._auth = auth_client or KISAuthClient()

    # ── 시장별 ───────────────────────────────────────────────
    def fetch_market_program_daily(
        self,
        market: str,
        start_date: str = "",
        end_date: str = "",
        market_div: str = "J",
    ) -> ProgramTradeSeries:
        """market ∈ {KOSPI, KOSDAQ}. 날짜 공백 시 ~당일. (최대 8개월 과거)"""
        params = {
            "FID_COND_MRKT_DIV_CODE": market_div,
            "FID_MRKT_CLS_CODE": _MARKET_CLS[market],
            "FID_INPUT_DATE_1": start_date or "",
            "FID_INPUT_DATE_2": end_date or "",
        }
        res = self._auth.url_fetch(_MARKET_PATH, _MARKET_TR_ID, "", params)
        if not res.isOK():
            res.printError(_MARKET_PATH)
            raise ValueError(
                f"KIS market-program call failed: "
                f"{res.getErrorCode()} - {res.getErrorMessage()}"
            )

        rows = _as_list(getattr(res.getBody(), "output", None))
        return ProgramTradeSeries(
            source="kis",
            scope="market",
            entity_code=market,
            observed_at=datetime.now(_KST),
            observations=_flatten(rows, _MARKET_COMBOS),
        )

    # ── 종목별 ───────────────────────────────────────────────
    def fetch_stock_program_daily(
        self,
        ticker: str,
        date: str = "",
        market_div: str = "J",
    ) -> ProgramTradeSeries:
        """ticker: 6자리. date 공백 시 당일부터 조회."""
        params = {
            "FID_COND_MRKT_DIV_CODE": market_div,
            "FID_INPUT_ISCD": ticker,
            "FID_INPUT_DATE_1": date or "",
        }
        res = self._auth.url_fetch(_STOCK_PATH, _STOCK_TR_ID, "", params)
        if not res.isOK():
            res.printError(_STOCK_PATH)
            raise ValueError(
                f"KIS stock-program call failed: "
                f"{res.getErrorCode()} - {res.getErrorMessage()}"
            )

        rows = _as_list(getattr(res.getBody(), "output", None))
        return ProgramTradeSeries(
            source="kis",
            scope="stock",
            entity_code=ticker,
            observed_at=datetime.now(_KST),
            observations=_flatten(rows, _STOCK_COMBOS),
        )


# ── module-level helpers ─────────────────────────────────────
def _flatten(rows: list, combos: list[tuple[str, str]]) -> list[ProgramTradeObservation]:
    obs: list[ProgramTradeObservation] = []
    for row in rows:
        raw_date = _get(row, "stck_bsop_date")
        if not raw_date:
            continue
        observation_date = _fmt_date(str(raw_date))
        for trade_class, account_type in combos:
            o = _extract(row, observation_date, trade_class, account_type)
            if o is not None:
                obs.append(o)
    return obs


def _extract(
    row: dict, observation_date: str, tc: str, ac: str
) -> Optional[ProgramTradeObservation]:
    """{tc}_{ac}_{side}_{metric} 필드명을 생성해 추출. 6개 모두 없으면 None."""
    prefix = f"{tc}_{ac}"
    vals = {
        "sell_vol": _to_decimal(_get(row, f"{prefix}_seln_vol")),
        "sell_amount": _to_decimal(_get(row, f"{prefix}_seln_tr_pbmn")),
        "buy_vol": _to_decimal(_get(row, f"{prefix}_shnu_vol")),
        "buy_amount": _to_decimal(_get(row, f"{prefix}_shnu_tr_pbmn")),
        "net_qty": _to_decimal(_get(row, f"{prefix}_ntby_qty")),
        "net_amount": _to_decimal(_get(row, f"{prefix}_ntby_tr_pbmn")),
    }
    if all(v is None for v in vals.values()):
        return None
    return ProgramTradeObservation(
        observation_date=observation_date,
        trade_class=tc,
        account_type=ac,
        **vals,
    )


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