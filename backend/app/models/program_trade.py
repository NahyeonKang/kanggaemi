"""
app/models/program_trade.py

프로그램매매 추이(일별) — long 테이블 (수급/flow 차원, investor_flow와 형제).

설계:
  - (trade_class, account_type)를 행으로 전개해 wide 폭증 회피.
      trade_class  : arbt(차익) | nabt(비차익) | whol(전체)
      account_type : entm(위탁) | onsl(자기)   | smtn(합계)
  - scope("market"|"stock") 통합.
      market scope: entity_code = "KOSPI" | "KOSDAQ", 최대 9행/일
      stock  scope: entity_code = 6자리 티커, (whol, smtn) 1행/일
  - 값 컬럼: 매도/매수/순매수 × {vol, amount} = 6.
    (investor_flow와 달리 종목 프로그램 API가 시장명을 안 줘서 market 컬럼 없음)
  - resolution daily. upsert + ingested_at.

NOTE(단위): 거래대금은 원(full KRW) 기준(정의서 예시값 기준). 원시값 저장.
NOTE(정정): 프로그램매매도 잠정→확정 정정 가능. 이력 보존 필요 시
  (..., observation_date, ingested_at) 유니크 + insert-on-change로 승격.
"""
from sqlalchemy import (
    BigInteger, Column, DateTime, Index, Numeric, String, UniqueConstraint,
)

from app.db.base import Base


class ProgramTradeDailyModel(Base):
    __tablename__ = "program_trade_daily"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    source = Column(String(16), nullable=False)            # "kis"
    scope = Column(String(8), nullable=False)              # "market" | "stock"
    entity_code = Column(String(16), nullable=False)       # KOSPI/KOSDAQ | 티커
    trade_class = Column(String(8), nullable=False)        # arbt | nabt | whol
    account_type = Column(String(8), nullable=False)       # entm | onsl | smtn
    observation_date = Column(String(10), nullable=False)  # "YYYY-MM-DD"
    sell_vol = Column(Numeric(24, 2))                      # 매도 거래량
    sell_amount = Column(Numeric(24, 2))                   # 매도 거래대금(원)
    buy_vol = Column(Numeric(24, 2))                       # 매수 거래량
    buy_amount = Column(Numeric(24, 2))                    # 매수 거래대금(원)
    net_qty = Column(Numeric(24, 2))                       # 순매수 수량
    net_amount = Column(Numeric(24, 2))                    # 순매수 거래대금(원)
    ingested_at = Column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "source", "scope", "entity_code",
            "trade_class", "account_type", "observation_date",
            name="uq_program_trade",
        ),
        Index(
            "ix_program_trade_lookup",
            "scope", "entity_code", "trade_class", "account_type", "observation_date",
        ),
    )