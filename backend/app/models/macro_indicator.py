"""
app/models/macro_indicator.py

매크로 지표 관측 시계열 (FRED·BOK, daily/monthly).
"""
from sqlalchemy import (
    BigInteger, Column, DateTime, Index, Numeric, String, UniqueConstraint,
)

from app.db.base import Base


class MacroObservationModel(Base):
    __tablename__ = "macro_observation"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    source = Column(String(16), nullable=False)            # "fred" | "bok"
    series_id = Column(String(32), nullable=False)
    resolution = Column(String(1), nullable=False)         # "D" | "M"
    observation_date = Column(String(10), nullable=False)  # "YYYY-MM-DD" (event date)
    value = Column(Numeric(18, 6))                         # nullable (결측)
    ingested_at = Column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "source", "series_id", "resolution", "observation_date",
            name="uq_macro_obs",
        ),
        Index("ix_macro_obs_lookup", "series_id", "resolution", "observation_date"),
    )