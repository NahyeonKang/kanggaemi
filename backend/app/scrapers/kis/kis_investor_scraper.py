"""
app/scrapers/kis/kis_investor_scraper.py

KIS 투자자별 매매동향(일별) 스크래퍼 — 수급(flow) 도메인.
인증(KISAuthClient)만 yield 스크래퍼와 공유하고, 도메인은 분리.

  - 시장별 [국내주식-075] FHPTJ04040000 : 페이징 없음, output(array).
  - 종목별            FHPTJ04160001 : output2(array) 페이징(M/F→N),
                                        output1에서 대표시장명 추출.

두 API의 NET 필드명이 동일하므로 INVESTOR_FIELDS 매핑으로 공통 flatten.
"""
import logging
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Optional
from zoneinfo import ZoneInfo

from app.schemas.investor_flow import InvestorFlowObservation, InvestorFlowSeries
from app.scrapers.kis.kis_auth import KISAuthClient, smart_sleep

logger = logging.getLogger(__name__)

_KST = ZoneInfo("Asia/Seoul")

_MARKET_PATH = "/uapi/domestic-stock/v1/quotations/inquire-investor-daily-by-market"
_MARKET_TR_ID = "FHPTJ04040000"
_STOCK_PATH = "/uapi/domestic-stock/v1/quotations/investor-trade-by-stock-daily"
_STOCK_TR_ID = "FHPTJ04160001"
_MAX_PAGES = 10

_MARKET_ISCD1 = {"KOSPI": "KSP", "KOSDAQ": "KSQ"}

# investor_type -> (순매수 수량 필드, 순매수 대금 필드). 두 API 공통.
INVESTOR_FIELDS: dict[str, tuple[str, str]] = {
    "frgn":      ("frgn_ntby_qty",      "frgn_ntby_tr_pbmn"),
    "frgn_reg":  ("frgn_reg_ntby_qty",  "frgn_reg_ntby_pbmn"),
    "frgn_nreg": ("frgn_nreg_ntby_qty", "frgn_nreg_ntby_pbmn"),
    "prsn":      ("prsn_ntby_qty",      "prsn_ntby_tr_pbmn"),
    "orgn":      ("orgn_ntby_qty",      "orgn_ntby_tr_pbmn"),
    "scrt":      ("scrt_ntby_qty",      "scrt_ntby_tr_pbmn"),
    "ivtr":      ("ivtr_ntby_qty",      "ivtr_ntby_tr_pbmn"),
    "pe_fund":   ("pe_fund_ntby_vol",   "pe_fund_ntby_tr_pbmn"),
    "bank":      ("bank_ntby_qty",      "bank_ntby_tr_pbmn"),
    "insu":      ("insu_ntby_qty",      "insu_ntby_tr_pbmn"),
    "mrbn":      ("mrbn_ntby_qty",      "mrbn_ntby_tr_pbmn"),
    "fund":      ("fund_ntby_qty",      "fund_ntby_tr_pbmn"),
    "etc":       ("etc_ntby_qty",       "etc_ntby_tr_pbmn"),
    "etc_orgt":  ("etc_orgt_ntby_vol",  "etc_orgt_ntby_tr_pbmn"),
    "etc_corp":  ("etc_corp_ntby_vol",  "etc_corp_ntby_tr_pbmn"),
}


class KISInvestorScraper:
    """Fetches investor trading flow (일별) from KIS."""

    def __init__(self, auth_client: Optional[KISAuthClient] = None) -> None:
        self._auth = auth_client or KISAuthClient()

    # ── 시장별 (페이징 없음) ─────────────────────────────────
    def fetch_market_investor_daily(
        self, market: str, sector_code: str = "0001", date: Optional[str] = None
    ) -> InvestorFlowSeries:
        """market ∈ {KOSPI, KOSDAQ}. date: YYYYMMDD(생략 시 오늘 KST)."""
        iscd1 = _MARKET_ISCD1[market]
        d = date or datetime.now(_KST).strftime("%Y%m%d")
        params = {
            "FID_COND_MRKT_DIV_CODE": "U",
            "FID_INPUT_ISCD": sector_code,
            "FID_INPUT_DATE_1": d,
            "FID_INPUT_ISCD_1": iscd1,
            "FID_INPUT_DATE_2": d,
            "FID_INPUT_ISCD_2": sector_code,
        }
        res = self._auth.url_fetch(_MARKET_PATH, _MARKET_TR_ID, "", params)
        if not res.isOK():
            res.printError(_MARKET_PATH)
            raise ValueError(
                f"KIS market-investor call failed: "
                f"{res.getErrorCode()} - {res.getErrorMessage()}"
            )

        rows = _as_list(getattr(res.getBody(), "output", None))
        return InvestorFlowSeries(
            source="kis",
            scope="market",
            market=market,
            entity_code=sector_code,
            observed_at=datetime.now(_KST),
            observations=_flatten(rows),
        )

    # ── 종목별 (output2 페이징) ──────────────────────────────
    def fetch_stock_investor_daily(
        self,
        ticker: str,
        date: Optional[str] = None,
        market_div: str = "J",
        etc_cls_code: str = "1",
    ) -> InvestorFlowSeries:
        """ticker: 6자리. date: YYYYMMDD(생략 시 오늘 KST). 당일은 15:40 이후 조회."""
        d = date or datetime.now(_KST).strftime("%Y%m%d")
        params = {
            "FID_COND_MRKT_DIV_CODE": market_div,    # J:KRX, NX:NXT, UN:통합
            "FID_INPUT_ISCD": ticker,
            "FID_INPUT_DATE_1": d,
            "FID_ORG_ADJ_PRC": "",
            "FID_ETC_CLS_CODE": etc_cls_code,        # 정의서: "1" 입력
        }

        output2: list[dict] = []
        market_name = "KOSPI"
        tr_cont = ""
        for page in range(_MAX_PAGES):
            res = self._auth.url_fetch(_STOCK_PATH, _STOCK_TR_ID, tr_cont, params)
            if not res.isOK():
                res.printError(_STOCK_PATH)
                raise ValueError(
                    f"KIS stock-investor call failed: "
                    f"{res.getErrorCode()} - {res.getErrorMessage()}"
                )

            body = res.getBody()
            o1 = getattr(body, "output1", None)
            if o1:
                market_name = _norm_market(_get(o1, "rprs_mrkt_kor_name"))
            output2.extend(_as_list(getattr(body, "output2", None)))

            tr_cont = res.getHeader().tr_cont
            if tr_cont not in ("M", "F"):
                break
            logger.info("Fetching next page of stock-investor (page=%d).", page + 1)
            tr_cont = "N"
            smart_sleep()

        return InvestorFlowSeries(
            source="kis",
            scope="stock",
            market=market_name,
            entity_code=ticker,
            observed_at=datetime.now(_KST),
            observations=_flatten(output2),
        )


# ── module-level helpers ─────────────────────────────────────
def _flatten(rows: list) -> list[InvestorFlowObservation]:
    """API 행(투자자별 wide) → (date × investor_type) long 관측으로 전개."""
    obs: list[InvestorFlowObservation] = []
    for row in rows:
        raw_date = _get(row, "stck_bsop_date")
        if not raw_date:
            continue
        observation_date = _fmt_date(str(raw_date))
        for itype, (qty_field, amount_field) in INVESTOR_FIELDS.items():
            obs.append(
                InvestorFlowObservation(
                    observation_date=observation_date,
                    investor_type=itype,
                    net_qty=_to_decimal(_get(row, qty_field)),
                    net_amount=_to_decimal(_get(row, amount_field)),
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


def _norm_market(name: Optional[str]) -> str:
    return "KOSDAQ" if name and "KOSDAQ" in str(name).upper() else "KOSPI"


def _fmt_date(yyyymmdd: str) -> str:
    """'YYYYMMDD' → 'YYYY-MM-DD'."""
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