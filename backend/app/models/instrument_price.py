"""
app/models/instrument_price.py

시세 도메인 (주식/업종/선물옵션 통합).

  - InstrumentOhlcvModel       : 3개 API의 output2를 통합. asset_class로 구분.
        (stock_price_ohlcv → instrument_ohlcv, asset_class 컬럼 추가)
  - StockValuationSnapshotModel: 주식 output1 (PER/EPS/PBR/시총). 컬럼 동일(무변경).
  - DerivativeSnapshotModel    : 선물옵션 output1 (베이시스·OI·괴리율·이론가).
        업종 output1은 빈약하여 스냅샷 생략.

OHLCV/스냅샷 모두 tz-aware. 가격은 지수·선물 소수점 위해 Numeric(18,4).
"""
from sqlalchemy import (
    BigInteger, Column, DateTime, Index, Numeric, String, UniqueConstraint,
)

from app.db.base import Base

class InstrumentOhlcvModel(Base):
    """기간별 OHLCV 시계열 — 주식/업종/선물옵션 통합 (output2)."""

    __tablename__ = "instrument_ohlcv"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    source = Column(String(16), nullable=False)            # "kis"
    asset_class = Column(String(8), nullable=False)        # stock|index|future|option
    entity_code = Column(String(16), nullable=False)       # 티커 | 업종코드 | 선물코드
    resolution = Column(String(1), nullable=False)         # D | W | M | Y
    observation_date = Column(String(10), nullable=False)  # "YYYY-MM-DD"
    open = Column(Numeric(18, 4))
    high = Column(Numeric(18, 4))
    low = Column(Numeric(18, 4))
    close = Column(Numeric(18, 4))
    volume = Column(Numeric(24, 2))                        # 누적 거래량
    amount = Column(Numeric(24, 2))                        # 누적 거래대금
    ingested_at = Column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "source", "asset_class", "entity_code", "resolution", "observation_date",
            name="uq_instrument_ohlcv",
        ),
        Index(
            "ix_instrument_ohlcv_lookup",
            "asset_class", "entity_code", "resolution", "observation_date",
        ),
    )


class StockValuationSnapshotModel(Base):
    """주식 밸류에이션 스냅샷 (output1). append-only."""

    __tablename__ = "stock_valuation_snapshot"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    source = Column(String(16), nullable=False)
    ticker = Column(String(12), nullable=False)
    observed_at = Column(DateTime(timezone=True), nullable=False)
    name = Column(String(64))
    current_price = Column(Numeric(18, 2))
    upper_limit = Column(Numeric(18, 2))
    lower_limit = Column(Numeric(18, 2))
    vol_turnover = Column(Numeric(12, 4))
    listed_shares = Column(Numeric(24, 2))
    market_cap = Column(Numeric(24, 2))                    # 억원
    per = Column(Numeric(14, 4))
    eps = Column(Numeric(18, 4))
    pbr = Column(Numeric(14, 4))
    ingested_at = Column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        UniqueConstraint("source", "ticker", "observed_at", name="uq_stock_valuation"),
        Index("ix_stock_valuation_asof", "ticker", "observed_at"),
    )


class DerivativeSnapshotModel(Base):
    """선물옵션 스냅샷 (output1): 베이시스·미결제약정·괴리율·이론가. append-only."""

    __tablename__ = "derivative_snapshot"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    source = Column(String(16), nullable=False)
    entity_code = Column(String(16), nullable=False)       # 선물옵션 종목코드
    observed_at = Column(DateTime(timezone=True), nullable=False)
    name = Column(String(64))
    current_price = Column(Numeric(18, 4))
    upper_limit = Column(Numeric(18, 4))
    lower_limit = Column(Numeric(18, 4))
    basis = Column(Numeric(14, 4))                         # 베이시스
    kospi200 = Column(Numeric(14, 4))                      # KOSPI200 지수
    open_interest = Column(Numeric(20, 2))                 # 미결제약정 수량
    oi_change = Column(Numeric(20, 2))                     # 미결제약정 증감
    theoretical_price = Column(Numeric(18, 4))             # 이론가
    disparity = Column(Numeric(12, 4))                     # 괴리율
    tick_strength = Column(Numeric(12, 4))                 # 체결강도
    ingested_at = Column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        UniqueConstraint("source", "entity_code", "observed_at", name="uq_derivative_snapshot"),
        Index("ix_derivative_asof", "entity_code", "observed_at"),
    )