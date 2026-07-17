"""
app/scrapers/kis/kis_financials_scraper.py

KIS 재무 4종 [079/080/081/082]을 결산기간(stac_yymm) 기준으로 병합 — financials 도메인.
4개 API가 동일 request(mrkt_div/iscd/div_cls) + output(stac_yymm 배열) 구조라
config로 순회하며 outer-merge. 페이징 없음.

  income-statement  FHKST66430200 : revenue(sale_account), op_income(bsop_prti)
  financial-ratio   FHKST66430300 : revenue_growth(grs), op_income_growth(bsop_prfi_inrt),
                                     net_income_growth(ntin_inrt), roe(roe_val), eps(eps)
  profit-ratio      FHKST66430400 : net_profit_margin(sale_ntin_rate)
  other-major-ratios FHKST66430500: ev_ebitda(ev_ebitda)
"""
import logging
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Optional
from zoneinfo import ZoneInfo

from app.schemas.stock_financials import FinancialsObservation, FinancialsSeries
from app.scrapers.kis.kis_auth import KISAuthClient

logger = logging.getLogger(__name__)

_KST = ZoneInfo("Asia/Seoul")
_BASE = "/uapi/domestic-stock/v1/finance"

# 순서대로 호출·병합. 각 (내부필드 -> KIS output 필드)
_FIN_CONFIG = [
    {
        "url": f"{_BASE}/income-statement", "tr_id": "FHKST66430200",
        "fields": {"revenue": "sale_account", "op_income": "bsop_prti"},
    },
    {
        "url": f"{_BASE}/financial-ratio", "tr_id": "FHKST66430300",
        "fields": {
            "revenue_growth": "grs", "op_income_growth": "bsop_prfi_inrt",
            "net_income_growth": "ntin_inrt", "roe": "roe_val", "eps": "eps",
        },
    },
    {
        "url": f"{_BASE}/profit-ratio", "tr_id": "FHKST66430400",
        "fields": {"net_profit_margin": "sale_ntin_rate"},
    },
    {
        "url": f"{_BASE}/other-major-ratios", "tr_id": "FHKST66430500",
        "fields": {"ev_ebitda": "ev_ebitda"},
    },
]

_PERIOD_TYPE = {"0": "annual", "1": "quarter"}


class KISFinancialsScraper:
    """Fetches & merges 4 KIS finance APIs by settlement period."""

    def __init__(self, auth_client: Optional[KISAuthClient] = None) -> None:
        self._auth = auth_client or KISAuthClient()

    def fetch_financials(
        self, ticker: str, div_cls_code: str = "0", market_div: str = "J"
    ) -> FinancialsSeries:
        """div_cls_code: 0=년(annual), 1=분기(quarter, 연누적)."""
        params = {
            "FID_COND_MRKT_DIV_CODE": market_div,
            "FID_INPUT_ISCD": ticker,
            "FID_DIV_CLS_CODE": div_cls_code,
        }

        merged: dict[str, dict] = {}
        for cfg in _FIN_CONFIG:
            rows = self._fetch_one(cfg["url"], cfg["tr_id"], params)
            for row in rows:
                yymm = _get(row, "stac_yymm")
                if not yymm:
                    continue
                bucket = merged.setdefault(str(yymm).strip(), {})
                for field, src in cfg["fields"].items():
                    bucket[field] = _to_decimal(_get(row, src))

        observations = [
            FinancialsObservation(stac_yymm=yymm, **vals)
            for yymm, vals in sorted(merged.items(), reverse=True)  # 최신 우선
        ]

        return FinancialsSeries(
            source="kis",
            ticker=ticker,
            period_type=_PERIOD_TYPE.get(div_cls_code, div_cls_code),
            observed_at=datetime.now(_KST),
            observations=observations,
        )

    def _fetch_one(self, url: str, tr_id: str, params: dict) -> list:
        res = self._auth.url_fetch(url, tr_id, "", params)
        if not res.isOK():
            res.printError(url)
            raise ValueError(
                f"KIS finance call failed ({tr_id}): "
                f"{res.getErrorCode()} - {res.getErrorMessage()}"
            )
        return _as_list(getattr(res.getBody(), "output", None))


# ── helpers ──────────────────────────────────────────────────
def _get(obj: object, key: str):
    if isinstance(obj, dict):
        return obj.get(key)
    return getattr(obj, key, None)


def _as_list(raw: object) -> list:
    if not raw:
        return []
    return raw if isinstance(raw, list) else [raw]


def _to_decimal(value: object) -> Optional[Decimal]:
    if value is None or str(value).strip() == "":
        return None
    try:
        return Decimal(str(value).strip())
    except (InvalidOperation, ValueError):
        return None