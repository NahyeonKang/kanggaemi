"""
app/models/macro_indicator.py

SQLAlchemy ORM model for persisted FRED macro indicator observations.
"""
from datetime import datetime

from sqlalchemy import Column, DateTime, Float, Integer, String, UniqueConstraint

from app.db.base import Base


class MacroIndicatorObservationModel(Base):
    """
    Persisted FRED macro indicator observation.

    Unique key: (source, series_id, observation_date)
    so that upserts can update the value without creating duplicates.
    """

    __tablename__ = "macro_indicator_observations"

    id               = Column(Integer,    primary_key=True, autoincrement=True)
    source           = Column(String(20), nullable=False)
    series_id        = Column(String(20), nullable=False, index=True)
    observation_date = Column(String(10), nullable=False, index=True)  # YYYY-MM-DD
    value            = Column(Float,      nullable=True)
    fetched_at       = Column(DateTime,   nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "source", "series_id", "observation_date",
            name="uq_macro_indicator_observation",
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<MacroIndicatorObservationModel "
            f"{self.series_id} {self.observation_date} = {self.value}>"
        )
