"""
app/models/market_funds.py

국내 증시자금 종합 [국내주식-193] — 일별 macro 유동성 지표.
고정된 소수 지표라 wide 테이블(exchange_rate_daily 패턴, value-change upsert).

단위: 금액 억원, amount_turnover는 % (정의서: 단위 억원 / 금액회전율 %).
출처: 금융투자협회(KOFIA) 자료를 KIS가 중계 → 오류·지연 가능(정정 가능성).

NOTE(정정): KOFIA 데이터는 지연·정정 가능 → 이력 보존이 필요하면
  (observation_date, ingested_at) 유니크 + insert-on-change로 승격.
"""
from sqlalchemy import (
    BigInteger, Column, DateTime, Index, Numeric, String, UniqueConstraint,
)

from app.db.base import Base


class MarketFundsDailyModel(Base):
    __tablename__ = "market_funds_daily"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    source = Column(String(16), nullable=False)              # "kis"
    observation_date = Column(String(10), nullable=False)    # "YYYY-MM-DD"
    customer_deposit = Column(Numeric(20, 2))                # 고객예탁금금액(억원)
    customer_deposit_change = Column(Numeric(20, 2))         # 고객예탁금 전일대비(억원, ±)
    amount_turnover = Column(Numeric(12, 4))                 # 금액회전율(%)
    receivable = Column(Numeric(20, 2))                      # 미수금액(억원)
    credit_loan_balance = Column(Numeric(20, 2))             # 신용융자잔고(억원)
    futures_deposit = Column(Numeric(20, 2))                 # 선물예수금금액(억원)
    ingested_at = Column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        UniqueConstraint("source", "observation_date", name="uq_market_funds"),
        Index("ix_market_funds_date", "observation_date"),
    )