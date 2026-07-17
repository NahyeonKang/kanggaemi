"""
scripts/load_overseas_future_master.py

ffcode.mst → overseas_future_master 테이블 적재.

실행:
  # 다운로드 후 적재
  python -m scripts.load_overseas_future_master --download --dir ./_master
  # 이미 받아둔 파일로 적재
  python -m scripts.load_overseas_future_master --path ./_master/ffcode.mst

currency는 ffcode.mst에 없음. 필요 시 --currency-json 으로 {srs_cd|exch_cd: cur} 주입.
"""
import argparse
import json
import logging
from pathlib import Path
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.db.base import Base
from app.db.session import engine, SessionLocal
from app.models.overseas_future_master import OverseasFutureMasterModel
from app.repositories.overseas_future_master_repository import (
    OverseasFutureMasterRepository,
)
from app.scrapers.kis.overseas_future_master import (
    download_ffcode_mst, parse_ffcode_mst,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def main() -> int:
    parser = argparse.ArgumentParser(description="Load ffcode.mst into DB.")
    parser.add_argument("--download", action="store_true", help="KIS에서 새로 다운로드")
    parser.add_argument("--dir", default="./_master", help="다운로드/해제 디렉터리")
    parser.add_argument("--path", default=None, help="기존 ffcode.mst 경로")
    parser.add_argument("--currency-json", default=None, help="{srs_cd|exch_cd: currency} JSON")
    args = parser.parse_args()

    # 테이블 보장(멱등)
    Base.metadata.create_all(bind=engine, tables=[OverseasFutureMasterModel.__table__], checkfirst=True)

    if args.download:
        mst_path = download_ffcode_mst(args.dir)
    elif args.path:
        mst_path = Path(args.path)
    else:
        mst_path = Path(args.dir) / "ffcode.mst"

    if not Path(mst_path).exists():
        logger.error("ffcode.mst not found: %s (use --download)", mst_path)
        return 1

    currency_map = None
    if args.currency_json:
        currency_map = json.loads(Path(args.currency_json).read_text(encoding="utf-8"))

    items = parse_ffcode_mst(mst_path)
    with_calc = sum(1 for r in items if r.calc_decimal is not None)
    logger.info("parsed=%d, with calc_decimal=%d", len(items), with_calc)

    db = SessionLocal()
    try:
        affected = OverseasFutureMasterRepository().upsert_items(db, items, currency_map)
    finally:
        db.close()
    logger.info("Done. upserted=%d", affected)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())