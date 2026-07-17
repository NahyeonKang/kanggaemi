"""
app/scrapers/kis/domestic_derivative_master.py

국내 선물옵션 종목마스터 다운로드/파싱.
  - 지수 선물옵션: fo_idx_code_mts.mst  (market_type="idx")
  - 주식 선물옵션: fo_stk_code_mts.mst  (market_type="stk")

두 파일 모두 파이프('|') 구분 + cp949. 컬럼 구조 동일(9열):
  상품종류 | 단축코드 | 표준코드 | 한글종목명 | ATM구분 | 행사가 |
  월물구분코드 | 기초자산 단축코드 | 기초자산 명

핵심 목적: 품목(기초자산)별 '현재 활성 만기물 종목코드'를 해석(resolve)하기 위한
후보 월물 목록 확보. 만기물 코드는 계속 바뀌므로 batch가 이 마스터에서 해석한다.

해외선물 ffcode.mst 로더와 동일한 패턴(다운로드 → 파싱 → 타입드 레코드).
고정폭이 아니라 '|' 구분이라 파싱은 단순.
"""
import logging
import ssl
import urllib.request
import zipfile
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, ConfigDict

logger = logging.getLogger(__name__)

_BASE_URL = "https://new.real.download.dws.co.kr/common/master"
_MST_SPEC = {
    "idx": {"zip": "fo_idx_code_mts.mst.zip", "mst": "fo_idx_code_mts.mst"},
    "stk": {"zip": "fo_stk_code_mts.mst.zip", "mst": "fo_stk_code_mts.mst"},
}

# 파이프 구분 컬럼 순서(0-based) — 레퍼런스와 동일
_COL = {
    "product_type": 0,     # 상품종류
    "srs_cd": 1,           # 단축코드 (수집에 쓰는 종목코드)
    "std_cd": 2,           # 표준코드
    "name": 3,             # 한글종목명
    "atm_div": 4,          # ATM구분
    "strike": 5,           # 행사가(옵션)
    "expiry_code": 6,      # 월물구분코드 (만기물 식별)
    "underlying_cd": 7,    # 기초자산 단축코드 (품목)
    "underlying_name": 8,  # 기초자산 명
}
_NCOLS = 9


class DomesticDerivativeMasterItem(BaseModel):
    """국내 선물옵션 마스터 한 행."""

    model_config = ConfigDict(from_attributes=True)

    market_type: str                          # "idx" | "stk"
    product_type: Optional[str] = None        # 상품종류(선물/콜/풋 등)
    srs_cd: str                               # 단축코드(종목코드)
    std_cd: Optional[str] = None              # 표준코드
    name: Optional[str] = None                # 한글종목명
    atm_div: Optional[str] = None             # ATM구분
    strike: Optional[str] = None              # 행사가(옵션)
    expiry_code: Optional[str] = None         # 월물구분코드
    underlying_cd: Optional[str] = None       # 기초자산 단축코드(품목)
    underlying_name: Optional[str] = None     # 기초자산 명


def download_domestic_derivative_mst(market_type: str, dest_dir: str | Path) -> Path:
    """fo_idx/fo_stk mst.zip 다운로드 후 해제. 해제된 .mst 경로 반환.

    NOTE: KIS 다운로드 도메인은 사내/컨테이너 네트워크에서 막힐 수 있음.
    """
    if market_type not in _MST_SPEC:
        raise ValueError(f"market_type must be one of {list(_MST_SPEC)}, got: {market_type!r}")
    spec = _MST_SPEC[market_type]
    dest = Path(dest_dir)
    dest.mkdir(parents=True, exist_ok=True)
    zip_path = dest / spec["zip"]

    ssl._create_default_https_context = ssl._create_unverified_context
    logger.info("Downloading %s ...", spec["zip"])
    urllib.request.urlretrieve(f"{_BASE_URL}/{spec['zip']}", zip_path)
    with zipfile.ZipFile(zip_path) as zf:
        zf.extractall(dest)
    mst_path = dest / spec["mst"]
    logger.info("Extracted: %s", mst_path)
    return mst_path


def parse_domestic_derivative_mst(
    mst_path: str | Path, market_type: str
) -> list[DomesticDerivativeMasterItem]:
    """파이프('|') 구분 cp949 파일 파싱."""
    items: list[DomesticDerivativeMasterItem] = []
    with open(mst_path, mode="r", encoding="cp949") as f:
        for line in f:
            row = line.rstrip("\n").rstrip("\r")
            if not row.strip():
                continue
            parts = row.split("|")
            if len(parts) < _NCOLS:
                logger.warning("skip malformed row (%d cols): %.60s", len(parts), row)
                continue
            items.append(_to_item(parts, market_type))
    logger.info("Parsed %d domestic-derivative master rows (%s).", len(items), market_type)
    return items


def _to_item(parts: list[str], market_type: str) -> DomesticDerivativeMasterItem:
    def cell(key: str) -> Optional[str]:
        v = parts[_COL[key]].strip()
        return v or None

    return DomesticDerivativeMasterItem(
        market_type=market_type,
        product_type=cell("product_type"),
        srs_cd=(cell("srs_cd") or ""),
        std_cd=cell("std_cd"),
        name=cell("name"),
        atm_div=cell("atm_div"),
        strike=cell("strike"),
        expiry_code=cell("expiry_code"),
        underlying_cd=cell("underlying_cd"),
        underlying_name=cell("underlying_name"),
    )


# 로컬 실행용(레퍼런스 대체): 다운로드→파싱→요약
if __name__ == "__main__":
    import os

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    for mt in ("idx", "stk"):
        p = download_domestic_derivative_mst(mt, os.getcwd())
        rows = parse_domestic_derivative_mst(p, mt)
        logger.info("%s total=%d", mt, len(rows))