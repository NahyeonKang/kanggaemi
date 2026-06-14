"""
app/models/exchange_rate.py

SQLAlchemy ORM models for persisted exchange rate data.
  - ExchangeRateSummaryModel: one intraday summary row per date
    (first/last round, daily low/high/avg)
  - ExchangeRateDailyModel:   one base-rate row per date (daily series)
"""
from sqlalchemy import Column, DateTime, Float, Integer, String, UniqueConstraint

from app.db.base import Base


class ExchangeRateSummaryModel(Base):
    """
    Persisted intraday USD/KRW summary.

    Unique key: (source, currency_code, target_date)
    so that upserts can refresh the summary without creating duplicates.
    """

    __tablename__ = "exchange_rate_summaries"

    id            = Column(Integer, primary_key=True, autoincrement=True)
    source        = Column(String(50), nullable=False)
    currency_code = Column(String(10), nullable=False, index=True)
    target_date   = Column(String(10), nullable=False, index=True)  # YYYY.MM.DD
    first_rate    = Column(Float,      nullable=False)              # 최초 회차
    last_rate     = Column(Float,      nullable=False)              # 최종 회차
    daily_low     = Column(Float,      nullable=False)              # 일최저
    daily_high    = Column(Float,      nullable=False)              # 일최고
    daily_avg     = Column(Float,      nullable=False)              # 일평균
    fetched_at    = Column(DateTime,   nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "source", "currency_code", "target_date",
            name="uq_exchange_rate_summary",
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<ExchangeRateSummaryModel "
            f"{self.currency_code} {self.target_date} "
            f"last={self.last_rate} avg={self.daily_avg}>"
        )


class ExchangeRateDailyModel(Base):
    """
    Persisted daily USD/KRW base rate (one row per date).

    Unique key: (source, currency_code, quote_date)
    so that upserts can update the base_rate without creating duplicates.
    """

    __tablename__ = "exchange_rate_daily_quotes"

    id            = Column(Integer, primary_key=True, autoincrement=True)
    source        = Column(String(50), nullable=False)
    currency_code = Column(String(10), nullable=False, index=True)
    quote_date    = Column(String(10), nullable=False, index=True)  # YYYY.MM.DD
    base_rate     = Column(Float,      nullable=False)             # 매매 기준율
    fetched_at    = Column(DateTime,   nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "source", "currency_code", "quote_date",
            name="uq_exchange_rate_daily",
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<ExchangeRateDailyModel "
            f"{self.currency_code} {self.quote_date} = {self.base_rate}>"
        )