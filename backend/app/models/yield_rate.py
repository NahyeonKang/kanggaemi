"""
app/models/yield_rate.py

금리 도메인 모델 (resolution 분리):
  - YieldObservationModel    : daily/monthly 공식 종가 (FRED·BOK).
  - YieldIntradaySnapshotModel: KIS 장중 스냅샷.
"""
from sqlalchemy import (
    BigInteger, Column, DateTime, Index, Numeric, String, UniqueConstraint,
)

from app.db.base import Base


class YieldObservationModel(Base):
    """daily/monthly 공식 종가 금리."""
 
    __tablename__ = "yield_observation"
 
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    source = Column(String(16), nullable=False)            # "fred" | "bok"
    country = Column(String(2), nullable=False)            # "US" | "KR"
    tenor = Column(String(16), nullable=False)             # "10Y", "CD91", ...
    resolution = Column(String(1), nullable=False)         # "D" | "M"
    observation_date = Column(String(10), nullable=False)  # "YYYY-MM-DD"
    close = Column(Numeric(18, 6))                         # nullable (결측)
    ingested_at = Column(DateTime(timezone=True), nullable=False)
 
    __table_args__ = (
        UniqueConstraint(
            "source", "country", "tenor", "resolution", "observation_date",
            name="uq_yield_obs",
        ),
        Index("ix_yield_obs_lookup", "country", "tenor", "resolution", "observation_date"),
    )
 
 
class YieldIntradaySnapshotModel(Base):
    """KIS 장중 금리 스냅샷. fetch마다 1행 append."""
 
    __tablename__ = "yield_intraday_snapshot"
 
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    source = Column(String(16), nullable=False)            # "kis"
    country = Column(String(2), nullable=False)
    tenor = Column(String(16), nullable=False)
    observed_at = Column(DateTime(timezone=True), nullable=False)   # valid time
    current_rate = Column(Numeric(18, 6))
    prdy_vrss_sign = Column(String(2))
    prdy_vrss = Column(Numeric(18, 6))
    prdy_ctrt = Column(Numeric(18, 6))
    base_date = Column(String(10))                         # KIS stck_bsop_date
    ingested_at = Column(DateTime(timezone=True), nullable=False)   # transaction time
 
    __table_args__ = (
        UniqueConstraint(
            "source", "country", "tenor", "observed_at",
            name="uq_yield_snapshot",
        ),
        Index("ix_yield_snapshot_asof", "country", "tenor", "observed_at"),
    )
