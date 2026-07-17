"""
scripts/create_market_funds_table.py

증시자금 테이블 최초 1회 생성.
  - market_funds_daily

실행: python -m scripts.create_market_funds_table
checkfirst=True 멱등.
"""
import logging
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.db.base import Base
from app.db.session import engine
from app.models.market_funds import MarketFundsDailyModel

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def create_tables() -> None:
    tables = [MarketFundsDailyModel.__table__]
    Base.metadata.create_all(bind=engine, tables=tables, checkfirst=True)
    for t in tables:
        logger.info("Ensured table: %s", t.name)
    logger.info("Done.")


if __name__ == "__main__":
    create_tables()