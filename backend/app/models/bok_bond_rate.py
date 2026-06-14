"""
app/models/bok_bond_rate.py

SQLAlchemy ORM model for persisted BOK (Bank of Korea) ECOS historical
bond rate observations.
"""
from sqlalchemy import Column, DateTime, Float, Integer, String, UniqueConstraint

from app.db.base import Base


class BOKBondRateModel(Base):
    """
    Persisted BOK ECOS historical bond rate observation.

    Unique key: (source, item_code, observation_date)
    so that upserts can update the value without creating duplicates.
    """

    __tablename__ = "bok_bond_rates"

    id               = Column(Integer,    primary_key=True, autoincrement=True)
    source           = Column(String(20), nullable=False)
    item_code        = Column(String(20), nullable=False, index=True)
    item_name        = Column(String(50), nullable=False)
    observation_date = Column(String(10), nullable=False, index=True)  # YYYY-MM-DD
    value            = Column(Float,      nullable=False)
    fetched_at       = Column(DateTime,   nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "source", "item_code", "observation_date",
            name="uq_bok_bond_rate",
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<BOKBondRateModel "
            f"{self.item_code} {self.observation_date} = {self.value}>"
        )
