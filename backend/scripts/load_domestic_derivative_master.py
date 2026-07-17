"""
scripts/load_domestic_derivative_master.py

fo_idx_code_mts.mst / fo_stk_code_mts.mst → domestic_derivative_master 테이블 적재.
해외선물 load_overseas_future_master 와 동형.

실행:
  # 지수 선물옵션만 다운로드 후 적재(현재 필요 범위)
  python -m scripts.load_domestic_derivative_master --download --market idx
  # 지수+주식 모두
  python -m scripts.load_domestic_derivative_master --download --market both
  # 이미 받아둔 파일로
  python -m scripts.load_domestic_derivative_master --market idx --path ./_master/fo_idx_code_mts.mst
"""
import argparse
import logging
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.db.base import Base
from app.db.session import engine, SessionLocal
from app.models.domestic_derivative_master import DomesticDerivativeMasterModel
from app.repositories.domestic_derivative_master_repository import (
    DomesticDerivativeMasterRepository,
)
from app.scrapers.kis.domestic_derivative_master import (
    download_domestic_derivative_mst, parse_domestic_derivative_mst, _MST_SPEC,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def _resolve_path(market: str, args) -> Path:
    if args.download:
        return download_domestic_derivative_mst(market, args.dir)
    if args.path:
        return Path(args.path)
    return Path(args.dir) / _MST_SPEC[market]["mst"]


def main() -> int:
    parser = argparse.ArgumentParser(description="Load domestic derivative master into DB.")
    parser.add_argument("--market", choices=["idx", "stk", "both"], default="idx")
    parser.add_argument("--download", action="store_true", help="KIS에서 새로 다운로드")
    parser.add_argument("--dir", default="./_master", help="다운로드/해제 디렉터리")
    parser.add_argument("--path", default=None, help="기존 .mst 경로(단일 market일 때만)")
    args = parser.parse_args()

    Base.metadata.create_all(
        bind=engine, tables=[DomesticDerivativeMasterModel.__table__], checkfirst=True
    )

    markets = ["idx", "stk"] if args.market == "both" else [args.market]
    if args.path and args.market == "both":
        logger.error("--path는 단일 market에서만 사용하세요.")
        return 1

    repo = DomesticDerivativeMasterRepository()
    total = 0
    db = SessionLocal()
    try:
        for market in markets:
            mst_path = _resolve_path(market, args)
            if not Path(mst_path).exists():
                logger.error("mst not found: %s (use --download)", mst_path)
                return 1
            items = parse_domestic_derivative_mst(mst_path, market)
            futures = sum(1 for r in items if (r.product_type or "").find("선물") >= 0)
            logger.info("%s parsed=%d (futures-like=%d)", market, len(items), futures)
            total += repo.upsert_items(db, items)
    finally:
        db.close()

    logger.info("Done. upserted=%d", total)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())