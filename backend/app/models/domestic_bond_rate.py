"""
app/models/domestic_bond_rate.py

SQLAlchemy ORM model for persisted KIS domestic bond interest rates.
"""
from sqlalchemy import Column, DateTime, Float, Integer, String, UniqueConstraint

from app.db.base import Base


class DomesticBondRateModel(Base):
    """
    Persisted KIS domestic bond rate (금리 종합/국내채권_금리) observation.

    Unique key: (source, market_div_code, screen_div_code, cls_code, rate_code, base_date)
    so that upserts can update the rate_value without creating duplicates.
    """

    __tablename__ = "domestic_bond_rates"

    id              = Column(Integer,    primary_key=True, autoincrement=True)
    source          = Column(String(20), nullable=False)
    market_div_code = Column(String(10), nullable=False, index=True)
    screen_div_code = Column(String(10), nullable=False)
    cls_code        = Column(String(10), nullable=False)
    rate_code       = Column(String(20), nullable=False)
    rate_name       = Column(String(50), nullable=False)
    rate_value      = Column(Float,      nullable=True)
    base_date       = Column(String(10), nullable=False, index=True)  # YYYY-MM-DD
    fetched_at      = Column(DateTime,   nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "source", "market_div_code", "screen_div_code", "cls_code", "rate_code", "base_date",
            name="uq_domestic_bond_rate",
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<DomesticBondRateModel "
            f"{self.rate_name} {self.base_date} = {self.rate_value}>"
        )
