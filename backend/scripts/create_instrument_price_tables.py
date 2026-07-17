"""
scripts/create_instrument_price_tables.py

통합 시세 테이블 생성.
  - instrument_ohlcv          (entity_code varchar(48), currency 포함 — 해외선물 반영)
  - stock_valuation_snapshot
  - derivative_snapshot

실행:
  python -m scripts.create_instrument_price_tables           # 없으면 생성(기존 유지)
  python -m scripts.create_instrument_price_tables --drop    # 기존 삭제 후 재생성(데이터 소실)

--drop 은 스키마가 바뀐 경우(예: entity_code 확대, currency 추가) 데이터를 버리고
새 스키마로 다시 만들 때 사용.
"""
import argparse
import logging
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.db.base import Base
from app.db.session import engine
from app.models.instrument_price import (
    InstrumentOhlcvModel, StockValuationSnapshotModel, DerivativeSnapshotModel,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def create_tables(drop: bool = False) -> None:
    tables = [
        InstrumentOhlcvModel.__table__,
        StockValuationSnapshotModel.__table__,
        DerivativeSnapshotModel.__table__,
    ]

    if drop:
        # 의존성 역순으로 삭제(현재는 상호 FK 없음). checkfirst로 없는 테이블은 무시.
        Base.metadata.drop_all(bind=engine, tables=tables, checkfirst=True)
        for t in tables:
            logger.info("Dropped table (if existed): %s", t.name)

    Base.metadata.create_all(bind=engine, tables=tables, checkfirst=True)
    for t in tables:
        logger.info("Ensured table: %s", t.name)
    logger.info("Done.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Create instrument price tables.")
    parser.add_argument(
        "--drop", action="store_true",
        help="기존 테이블을 삭제 후 재생성(데이터 소실).",
    )
    args = parser.parse_args()
    create_tables(drop=args.drop)