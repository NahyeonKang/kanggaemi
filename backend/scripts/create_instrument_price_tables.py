"""
scripts/create_instrument_price_tables.py

통합 시세 테이블 최초 1회 생성.
  - instrument_ohlcv
  - stock_valuation_snapshot
  - derivative_snapshot

실행: python -m scripts.create_instrument_price_tables
"""
import sys
import os
import logging
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.db.base import Base
from app.db.session import engine
from app.models.instrument_price import (
    InstrumentOhlcvModel, StockValuationSnapshotModel, DerivativeSnapshotModel,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def create_tables() -> None:
    tables = [
        InstrumentOhlcvModel.__table__,
        StockValuationSnapshotModel.__table__,
        DerivativeSnapshotModel.__table__,
    ]
    Base.metadata.create_all(bind=engine, tables=tables, checkfirst=True)
    for t in tables:
        logger.info("Ensured table: %s", t.name)
    logger.info("Done.")


if __name__ == "__main__":
    create_tables()