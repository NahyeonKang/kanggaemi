"""
app/scrapers/kis/kis_scraper.py

KIS (Korea Investment & Securities) Open API scraper for domestic bond
interest rates: 업종/기타 > 금리 종합(국내채권_금리) [국내주식-155].

A single call returns ALL bond types at once in output1; the yield_snapshot
service filters the result by bcdt_code to extract the tenors it persists.
"""
import logging
from datetime import datetime
from typing import Optional

from app.schemas.yield_rate import KISCompInterestData, KISCompInterestItem
from app.scrapers.kis.kis_auth import KISAuthClient, smart_sleep

logger = logging.getLogger(__name__)

_TR_ID = "FHPST07020000"
_COMP_INTEREST_PATH = "/uapi/domestic-stock/v1/quotations/comp-interest"
_MAX_PAGES = 10


class KISScraper:
    """Fetches domestic bond interest rates from the KIS comp-interest API."""

    def __init__(self, auth_client: Optional[KISAuthClient] = None) -> None:
        self._auth_client = auth_client or KISAuthClient()

    def fetch_comp_interest(
        self,
        fid_cond_mrkt_div_code: str,
        fid_cond_scr_div_code: str,
        fid_div_cls_code: str,
        fid_div_cls_code1: str = "",
    ) -> KISCompInterestData:
        """
        Fetch 금리 종합(국내채권_금리) data via the KIS comp-interest API.

        Follows continuation pages (tr_cont "M"/"F" in the response header)
        until exhausted or _MAX_PAGES is reached.

        Raises:
            ValueError: If the API responds with rt_cd != "0".
        """
        params = {
            "FID_COND_MRKT_DIV_CODE": fid_cond_mrkt_div_code,
            "FID_COND_SCR_DIV_CODE": fid_cond_scr_div_code,
            "FID_DIV_CLS_CODE": fid_div_cls_code,
            "FID_DIV_CLS_CODE1": fid_div_cls_code1,
        }

        output1: list[KISCompInterestItem] = []
        tr_cont = ""

        for page in range(_MAX_PAGES):
            res = self._auth_client.url_fetch(_COMP_INTEREST_PATH, _TR_ID, tr_cont, params)

            if not res.isOK():
                res.printError(_COMP_INTEREST_PATH)
                raise ValueError(
                    f"KIS comp-interest call failed: "
                    f"{res.getErrorCode()} - {res.getErrorMessage()}"
                )

            body = res.getBody()
            output1.extend(_parse_items(getattr(body, "output1", None)))

            tr_cont = res.getHeader().tr_cont
            if tr_cont not in ("M", "F"):
                break

            logger.info("Fetching next page of comp-interest data (page=%d).", page + 1)
            tr_cont = "N"
            smart_sleep()

        return KISCompInterestData(
            source="kis",
            output1=output1,
            fetched_at=datetime.utcnow().isoformat(),
        )


def _parse_items(raw: object) -> list[KISCompInterestItem]:
    if not raw:
        return []
    rows = raw if isinstance(raw, list) else [raw]
    return [
        KISCompInterestItem(
            bcdt_code=row.get("bcdt_code", ""),
            hts_kor_isnm=row.get("hts_kor_isnm", ""),
            bond_mnrt_prpr=row.get("bond_mnrt_prpr", ""),
            prdy_vrss_sign=row.get("prdy_vrss_sign"),
            bond_mnrt_prdy_vrss=row.get("bond_mnrt_prdy_vrss"),
            prdy_ctrt=row.get("prdy_ctrt"),
            stck_bsop_date=row.get("stck_bsop_date", ""),
        )
        for row in rows
    ]
