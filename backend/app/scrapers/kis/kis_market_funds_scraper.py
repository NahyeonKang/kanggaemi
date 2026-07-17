"""
app/scrapers/kis/kis_market_funds_scraper.py

KIS 국내 증시자금 종합 [국내주식-193] 스크래퍼 — macro 유동성 도메인.
인증만 공유. 페이징 없음(tr_cont 다음조회 불가). 기준일에서 과거로 시계열 반환.
"""
import logging
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Optional
from zoneinfo import ZoneInfo

from app.schemas.market_funds import MarketFundsObservation, MarketFundsSeries
from app.scrapers.kis.kis_auth import KISAuthClient

logger = logging.getLogger(__name__)

_KST = ZoneInfo("Asia/Seoul")
_PATH = "/uapi/domestic-stock/v1/quotations/mktfunds"
_TR_ID = "FHKST649100C0"

# 내부 필드 → KIS output 필드
_FIELD_MAP = {
    "customer_deposit": "cust_dpmn_amt",            # 고객예탁금금액(억원)
    "customer_deposit_change": "cust_dpmn_amt_prdy_vrss",  # 전일대비(억원)
    "amount_turnover": "amt_tnrt",                  # 금액회전율(%)
    "receivable": "uncl_amt",                       # 미수금액(억원)
    "credit_loan_balance": "crdt_loan_rmnd",        # 신용융자잔고(억원)
    "futures_deposit": "futs_tfam_amt",             # 선물예수금금액(억원)
}


class KISMarketFundsScraper:
    """Fetches domestic market-funds (증시자금 종합) from KIS."""

    def __init__(self, auth_client: Optional[KISAuthClient] = None) -> None:
        self._auth = auth_client or KISAuthClient()

    def fetch_market_funds(self, date: str = "") -> MarketFundsSeries:
        """date: 기준일 YYYYMMDD(생략 시 오늘 KST). 그 날짜에서 과거로 시계열 반환."""
        d = date or datetime.now(_KST).strftime("%Y%m%d")
        params = {"FID_INPUT_DATE_1": d}

        res = self._auth.url_fetch(_PATH, _TR_ID, "", params)
        if not res.isOK():
            res.printError(_PATH)
            raise ValueError(
                f"KIS mktfunds call failed: "
                f"{res.getErrorCode()} - {res.getErrorMessage()}"
            )

        rows = _as_list(getattr(res.getBody(), "output", None))
        return MarketFundsSeries(
            source="kis",
            observed_at=datetime.now(_KST),
            observations=_flatten(rows),
        )


# ── parsing ──────────────────────────────────────────────────
def _flatten(rows: list) -> list[MarketFundsObservation]:
    obs: list[MarketFundsObservation] = []
    for row in rows:
        raw_date = _get(row, "bsop_date")
        if not raw_date:
            continue
        obs.append(
            MarketFundsObservation(
                observation_date=_fmt_date(str(raw_date).strip()),
                **{
                    field: _to_decimal(_get(row, src))
                    for field, src in _FIELD_MAP.items()
                },
            )
        )
    return obs


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