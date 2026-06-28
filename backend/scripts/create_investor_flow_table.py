"""
scripts/create_investor_flow_table.py

수급 테이블 최초 1회 생성.
  - investor_flow_daily

실행: python -m scripts.create_investor_flow_table
checkfirst=True 멱등.
"""
import sys
import os
import logging
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.db.base import Base
from app.db.session import engine
from app.models.investor_flow import InvestorFlowDailyModel

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def create_tables() -> None:
    tables = [InvestorFlowDailyModel.__table__]
    Base.metadata.create_all(bind=engine, tables=tables, checkfirst=True)
    for t in tables:
        logger.info("Ensured table: %s", t.name)
    logger.info("Done.")


if __name__ == "__main__":
    create_tables()