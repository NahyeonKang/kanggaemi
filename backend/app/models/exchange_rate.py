"""
app/models/exchange_rate.py

SQLAlchemy ORM model for persisted exchange rate quotes.
"""
from datetime import datetime

from sqlalchemy import Column, DateTime, Float, Integer, String, UniqueConstraint

from app.db.base import Base


class ExchangeRateQuoteModel(Base):
    """
    Persisted intraday USD/KRW exchange rate quote.

    Unique key: (source, currency_code, target_date, quote_time)
    so that upserts can update the base_rate without creating duplicates.
    """

    __tablename__ = "exchange_rate_quotes"

    id            = Column(Integer, primary_key=True, autoincrement=True)
    source        = Column(String(50), nullable=False)
    currency_code = Column(String(10), nullable=False, index=True)
    target_date   = Column(String(10), nullable=False, index=True)  # YYYY.MM.DD
    quote_time    = Column(String(8),  nullable=False)              # HH:MM:SS
    base_rate     = Column(Float,      nullable=False)
    fetched_at    = Column(DateTime,   nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "source", "currency_code", "target_date", "quote_time",
            name="uq_exchange_rate_quote",
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<ExchangeRateQuoteModel "
            f"{self.currency_code} {self.target_date} {self.quote_time} "
            f"= {self.base_rate}>"
        )
