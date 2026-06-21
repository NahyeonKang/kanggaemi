"""
app/models/exchange_rate.py

SQLAlchemy ORM models for persisted exchange rate data.
"""
from sqlalchemy import (
    BigInteger,
    Column,
    DateTime,
    Index,
    Numeric,
    String,
    UniqueConstraint,
)

from app.db.base import Base


class ExchangeRateIntradaySnapshotModel(Base):
    """장중 요약 스냅샷. 덮어쓰지 않고 fetch마다 1행 append."""
 
    __tablename__ = "exchange_rate_intraday_snapshot"
 
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    source = Column(String(32), nullable=False)
    base_ccy = Column(String(3), nullable=False)        # "USD"
    quote_ccy = Column(String(3), nullable=False)       # "KRW"
    target_date = Column(String(10), nullable=False)    # "YYYY.MM.DD" (event date)
    observed_at = Column(DateTime(timezone=True), nullable=False)   # valid time (snapshot)
    first_rate = Column(Numeric(18, 6))
    last_rate = Column(Numeric(18, 6))
    daily_low = Column(Numeric(18, 6))
    daily_high = Column(Numeric(18, 6))
    daily_avg = Column(Numeric(18, 6))
    ingested_at = Column(DateTime(timezone=True), nullable=False)   # transaction time (DB write)
 
    __table_args__ = (
        UniqueConstraint(
            "source", "base_ccy", "quote_ccy", "target_date", "observed_at",
            name="uq_fx_intraday_snapshot",
        ),
        # as-of 조회 가속: (통화쌍, 거래일, observed_at)
        Index(
            "ix_fx_intraday_asof",
            "base_ccy", "quote_ccy", "target_date", "observed_at",
        ),
    )
 
 
class ExchangeRateDailyModel(Base):
    """
    일별 매매기준율.
 
    KB 고시 기준환율은 거래일당 확정되고 실무상 정정이 없어 upsert(1행/일) 유지.
    """
 
    __tablename__ = "exchange_rate_daily"
 
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    source = Column(String(32), nullable=False)
    base_ccy = Column(String(3), nullable=False)
    quote_ccy = Column(String(3), nullable=False)
    quote_date = Column(String(10), nullable=False)     # "YYYY.MM.DD" (event date)
    base_rate = Column(Numeric(18, 6), nullable=False)
    ingested_at = Column(DateTime(timezone=True), nullable=False)   # transaction time (DB write)
 
    __table_args__ = (
        UniqueConstraint(
            "source", "base_ccy", "quote_ccy", "quote_date",
            name="uq_fx_daily",
        ),
        Index("ix_fx_daily_lookup", "base_ccy", "quote_ccy", "quote_date"),
    )