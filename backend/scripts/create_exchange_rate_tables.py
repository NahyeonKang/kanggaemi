"""
scripts/create_exchange_rate_tables.py

환율 테이블 최초 1회 생성 스크립트.
  - exchange_rate_intraday_snapshot
  - exchange_rate_daily

실행:
    python -m scripts.create_exchange_rate_tables

특징:
  - 모델 정의를 단일 소스로 사용(DDL 수기 작성 X → 드리프트 방지).
  - tables=[...]로 이 두 개만 생성(다른 도메인 테이블은 건드리지 않음).
  - checkfirst=True로 멱등 — 이미 있으면 건너뜀(에러 없음).
"""
import sys
import os
import logging
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.db.base import Base          # ← Base 경로
from app.db.session import engine      # ← engine 경로 (get_db와 같은 모듈일 가능성 높음)

# 모델을 import해야 Base.metadata에 테이블이 등록된다.
from app.models.exchange_rate import (
    ExchangeRateIntradaySnapshotModel,
    ExchangeRateDailyModel,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def create_tables() -> None:
    tables = [
        ExchangeRateIntradaySnapshotModel.__table__,
        ExchangeRateDailyModel.__table__,
    ]
    logger.info("Creating %d table(s) if not present...", len(tables))
    Base.metadata.create_all(bind=engine, tables=tables, checkfirst=True)
    for t in tables:
        logger.info("Ensured table: %s", t.name)
    logger.info("Done.")


if __name__ == "__main__":
    create_tables()