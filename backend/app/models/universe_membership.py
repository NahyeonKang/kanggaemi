"""Point-in-time membership snapshots for the configured stock universe."""

from sqlalchemy import BigInteger, Column, DateTime, Index, Integer, Numeric, String, UniqueConstraint

from app.db.base import Base


class UniverseMembershipModel(Base):
    __tablename__ = "universe_membership"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    univ_date = Column(String(10), nullable=False)  # YYYY-MM-DD, KST market date
    market = Column(String(12), nullable=False)
    ticker = Column(String(12), nullable=False)
    rank = Column(Integer, nullable=False)
    market_cap = Column(Numeric(20, 2))
    ingested_at = Column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        UniqueConstraint("univ_date", "market", "ticker", name="uq_universe_membership"),
        Index("ix_universe_membership_latest", "univ_date", "market", "rank"),
    )

