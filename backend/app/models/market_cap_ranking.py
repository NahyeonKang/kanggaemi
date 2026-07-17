"""
app/models/market_cap_ranking.py

국내주식 시가총액 상위 [국내주식-091] — 시장별 시총 순위 스냅샷.
유니버스(시총상위) 생성의 소스. 시장(market)별로 순위/시총/시총비중을 일자 스냅샷.

market: kospi(0001) | kosdaq(1001) | kospi200(2001) | all(0000).
단위: market_cap 억원, market_weight %.
"""
from sqlalchemy import (
    BigInteger, Column, DateTime, Index, Integer, Numeric, String, UniqueConstraint,
)

from app.db.base import Base


class MarketCapRankingModel(Base):
    __tablename__ = "market_cap_ranking"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    source = Column(String(16), nullable=False)            # "kis"
    market = Column(String(12), nullable=False)            # kospi|kosdaq|kospi200|all
    observation_date = Column(String(10), nullable=False)  # "YYYY-MM-DD"
    rank = Column(Integer, nullable=False)                 # 시총 순위(시장 내)
    ticker = Column(String(12), nullable=False)            # 종목코드
    name = Column(String(64))                              # 종목명
    close_price = Column(Numeric(18, 2))                   # 현재가(스냅샷 시점)
    volume = Column(Numeric(24, 2))                        # 누적 거래량
    listed_shares = Column(Numeric(24, 2))                 # 상장 주수
    market_cap = Column(Numeric(20, 2))                    # 시가총액(억원)
    market_weight = Column(Numeric(8, 4))                  # 시장전체 시총 비중(%)
    ingested_at = Column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        UniqueConstraint("source", "market", "observation_date", "ticker",
                         name="uq_market_cap_ranking"),
        Index("ix_market_cap_rank", "market", "observation_date", "rank"),
    )