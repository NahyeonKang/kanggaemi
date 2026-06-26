"""
scripts/create_yield_macro_tables.py

yield/macro 테이블 최초 1회 생성.
  - macro_observation
  - yield_observation
  - yield_intraday_snapshot

실행: python -m scripts.create_yield_macro_tables
checkfirst=True 멱등.
"""
import sys
import os
import logging
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.db.base import Base
from app.db.session import engine      # ← engine 경로
from app.models.macro_indicator import MacroObservationModel
from app.models.yield_rate import YieldObservationModel, YieldIntradaySnapshotModel

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def create_tables() -> None:
    tables = [
        MacroObservationModel.__table__,
        YieldObservationModel.__table__,
        YieldIntradaySnapshotModel.__table__,
    ]
    Base.metadata.create_all(bind=engine, tables=tables, checkfirst=True)
    for t in tables:
        logger.info("Ensured table: %s", t.name)
    logger.info("Done.")


if __name__ == "__main__":
    create_tables()