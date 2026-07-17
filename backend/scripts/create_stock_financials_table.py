"""
scripts/create_stock_financials_table.py

재무 테이블 생성 + (EPS 이관) 기존 valuation 테이블의 eps 컬럼 제거.

  1) stock_financials 테이블 생성(멱등)
  2) --drop-valuation-eps 지정 시: stock_valuation_snapshot.eps 컬럼 삭제(멱등)
     (EPS는 이제 stock_financials에서 관리 → 기존 컬럼 제거)

실행:
  python -m scripts.create_stock_financials_table
  python -m scripts.create_stock_financials_table --drop-valuation-eps
"""
import argparse
import logging
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sqlalchemy import text

from app.db.base import Base
from app.db.session import engine
from app.models.stock_financials import StockFinancialsModel

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

_Q_EPS_EXISTS = text(
    "SELECT 1 FROM information_schema.columns "
    "WHERE table_name = 'stock_valuation_snapshot' AND column_name = 'eps' "
    "AND table_schema = current_schema()"
)


def create_tables() -> None:
    Base.metadata.create_all(
        bind=engine, tables=[StockFinancialsModel.__table__], checkfirst=True
    )
    logger.info("Ensured table: stock_financials")


def drop_valuation_eps() -> None:
    with engine.begin() as conn:
        if conn.execute(_Q_EPS_EXISTS).first() is None:
            logger.info("skip: stock_valuation_snapshot.eps already absent.")
            return
        conn.execute(text("ALTER TABLE stock_valuation_snapshot DROP COLUMN eps"))
        logger.info("Dropped column: stock_valuation_snapshot.eps")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Create financials table (+ drop valuation eps).")
    parser.add_argument(
        "--drop-valuation-eps", action="store_true",
        help="stock_valuation_snapshot의 eps 컬럼 삭제(EPS 이관).",
    )
    args = parser.parse_args()

    create_tables()
    if args.drop_valuation_eps:
        drop_valuation_eps()
    logger.info("Done.")