"""
app/schemas/domestic_bond_rate.py

Pydantic schemas for the domestic bond rate domain.

Scraper-layer schemas (DomesticBondRateItem, DomesticBondRateData,
DomesticBondRateRecord) are used internally by KISDomesticBondRateScraper
and the service layer.

API-layer schemas (DomesticBondRateSyncRequest, DomesticBondRateSyncResponse,
DomesticBondRateResponse) are used by the FastAPI router.
"""
from typing import Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Scraper-layer schemas
# ---------------------------------------------------------------------------


class DomesticBondRateItem(BaseModel):
    """Single bond rate row from KIS comp-interest output1/output2."""

    bcdt_code: str                              # 자료코드
    hts_kor_isnm: str                           # HTS한글종목명
    bond_mnrt_prpr: str                         # 채권금리현재가
    prdy_vrss_sign: Optional[str] = None        # 전일대비부호
    bond_mnrt_prdy_vrss: Optional[str] = None   # 채권금리전일대비
    prdy_ctrt: Optional[str] = None             # 전일대비율 (output1)
    bstp_nmix_prdy_ctrt: Optional[str] = None   # 업종지수전일대비율 (output2)
    stck_bsop_date: str                         # 주식영업일자 (YYYYMMDD)


class DomesticBondRateData(BaseModel):
    """Normalized comp-interest result returned by KISDomesticBondRateScraper."""

    source: str = "kis"
    market_div_code: str
    screen_div_code: str
    cls_code: str
    cls_code1: str = ""
    output1: list[DomesticBondRateItem] = Field(default_factory=list)
    output2: list[DomesticBondRateItem] = Field(default_factory=list)
    fetched_at: str


class DomesticBondRateRecord(BaseModel):
    """A single normalized row ready for persistence."""

    source: str
    market_div_code: str
    screen_div_code: str
    cls_code: str
    rate_code: str
    rate_name: str
    rate_value: Optional[float] = None
    base_date: str   # YYYY-MM-DD
    fetched_at: str


# ---------------------------------------------------------------------------
# API-layer schemas
# ---------------------------------------------------------------------------


class DomesticBondRateSyncRequest(BaseModel):
    """Request body for POST /domestic-bond-rate/sync."""

    fid_cond_mrkt_div_code: str
    fid_cond_scr_div_code: str
    fid_div_cls_code: str
    fid_div_cls_code1: str = ""


class DomesticBondRateSyncResponse(BaseModel):
    """Response body for POST /domestic-bond-rate/sync."""

    source: str
    market_div_code: str
    screen_div_code: str
    cls_code: str
    affected_count: int


class DomesticBondRateResponse(BaseModel):
    """Single domestic bond rate row for GET /domestic-bond-rate/rates responses."""

    source: str
    market_div_code: str
    screen_div_code: str
    cls_code: str
    rate_code: str
    rate_name: str
    rate_value: Optional[float] = None
    base_date: str
    fetched_at: str

    model_config = {"from_attributes": True}
