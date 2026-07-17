"""
app/scrapers/kis/overseas_future_master.py

해외선물옵션 종목마스터(ffcode.mst) 다운로드/파싱.
KIS 레퍼런스 스크립트의 고정폭 슬라이싱을 그대로 보존하되, pandas 행단위 .loc
누적(느림)을 제거하고 타입드 레코드로 반환한다.

핵심 목적: 종목/품목별 '계산 소수점'(sCalcDesz)을 확보해 해외선물 시세 보정에 사용.
  (해외선물 원시 시세는 sCalcDesz만큼 소수점 이동 필요. 예: 6A=-4 → 6882.5 → 0.68825)

주의:
  - ffcode.mst에는 통화(currency) 필드가 없음 → currency는 별도 주입.
  - 슬라이스 오프셋은 레퍼런스와 동일(라인의 개행 포함 상태에서 음수 인덱스 사용).
    즉 `for row in f`가 주는 라인을 그대로 슬라이싱한다(수정 금지).
"""
import logging
import ssl
import urllib.request
import zipfile
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, ConfigDict

logger = logging.getLogger(__name__)

MST_URL = "https://new.real.download.dws.co.kr/common/master/ffcode.mst.zip"


class OverseasFutureMasterItem(BaseModel):
    """ffcode.mst 한 행(종목)."""

    model_config = ConfigDict(from_attributes=True)

    srs_cd: str                              # 종목코드 (예: 6AM24)
    name: Optional[str] = None               # 종목한글명
    exch_cd: Optional[str] = None            # 거래소코드 (ISAM KEY 1, 예: CME)
    product_code: Optional[str] = None       # 품목코드 (ISAM KEY 2, 예: 6A)
    product_type: Optional[str] = None       # 품목종류
    disp_decimal: Optional[int] = None       # 출력 소수점
    calc_decimal: Optional[int] = None       # 계산 소수점 (sCalcDesz) ★
    tick_size: Optional[str] = None          # 틱사이즈
    tick_value: Optional[str] = None         # 틱가치
    contract_size: Optional[str] = None      # 계약크기
    price_base: Optional[str] = None         # 가격표시진법
    mult: Optional[str] = None               # 환산승수
    sub_exch_cd: Optional[str] = None        # 서브 거래소 코드


def download_ffcode_mst(dest_dir: str | Path) -> Path:
    """ffcode.mst.zip 다운로드 후 압축 해제. 해제된 ffcode.mst 경로 반환.

    NOTE: KIS 다운로드 도메인은 사내/컨테이너 네트워크에서 막힐 수 있음.
    """
    dest = Path(dest_dir)
    dest.mkdir(parents=True, exist_ok=True)
    zip_path = dest / "ffcode.mst.zip"

    # 레퍼런스와 동일하게 인증서 검증 비활성(다운로드 서버 이슈 회피)
    ssl._create_default_https_context = ssl._create_unverified_context
    logger.info("Downloading ffcode.mst.zip ...")
    urllib.request.urlretrieve(MST_URL, zip_path)
    with zipfile.ZipFile(zip_path) as zf:
        zf.extractall(dest)
    mst_path = dest / "ffcode.mst"
    logger.info("Extracted: %s", mst_path)
    return mst_path


def parse_ffcode_mst(mst_path: str | Path) -> list[OverseasFutureMasterItem]:
    """고정폭 cp949 파일을 파싱. 슬라이스 오프셋은 레퍼런스와 동일."""
    items: list[OverseasFutureMasterItem] = []
    with open(mst_path, mode="r", encoding="cp949") as f:
        for row in f:
            if not row.strip():
                continue
            items.append(_parse_row(row))
    logger.info("Parsed %d overseas-future master rows.", len(items))
    return items


def build_calc_decimal_map(
    items: list[OverseasFutureMasterItem], by: str = "srs_cd"
) -> dict[str, int]:
    """{key: calc_decimal} 매핑. by='srs_cd'(종목) 또는 'product_code'(품목)."""
    result: dict[str, int] = {}
    for it in items:
        key = it.srs_cd if by == "srs_cd" else it.product_code
        if key and it.calc_decimal is not None:
            result[key] = it.calc_decimal
    return result


# ── parsing (레퍼런스 슬라이스 보존) ─────────────────────────
def _parse_row(row: str) -> OverseasFutureMasterItem:
    return OverseasFutureMasterItem(
        srs_cd=row[0:32].rstrip(),
        name=(row[82:107].rstrip() or None),
        exch_cd=(row[-92:-82].rstrip() or None),
        product_code=(row[-82:-72].rstrip() or None),
        product_type=(row[-72:-69].rstrip() or None),
        disp_decimal=_to_int(row[-69:-64]),
        calc_decimal=_to_int(row[-64:-59]),
        tick_size=(row[-59:-45].rstrip() or None),
        tick_value=(row[-45:-31].rstrip() or None),
        contract_size=(row[-31:-21].rstrip() or None),
        price_base=(row[-21:-17].rstrip() or None),
        mult=(row[-17:-7].rstrip() or None),
        sub_exch_cd=(row[-3:].rstrip() or None),
    )


def _to_int(value: str) -> Optional[int]:
    s = (value or "").strip()
    if not s:
        return None
    try:
        return int(s)
    except ValueError:
        return None


# 로컬 실행용(레퍼런스 대체): 다운로드→파싱→요약 출력
if __name__ == "__main__":
    import os

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    path = download_ffcode_mst(os.getcwd())
    rows = parse_ffcode_mst(path)
    logger.info("total=%d, with calc_decimal=%d",
                len(rows), sum(1 for r in rows if r.calc_decimal is not None))