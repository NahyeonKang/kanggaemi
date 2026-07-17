"""KIS KOSPI/KOSDAQ stock master used for agent asset grounding."""

from sqlalchemy import BigInteger, Column, DateTime, Index, Integer, String, UniqueConstraint

from app.db.base import Base


class DomesticStockMasterModel(Base):
    __tablename__ = "domestic_stock_master"

    id = Column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    market = Column(String(8), nullable=False)  # KOSPI | KOSDAQ
    ticker = Column(String(12), nullable=False)
    standard_code = Column(String(20))
    name = Column(String(128), nullable=False)
    sector_large_code = Column(String(8))
    sector_medium_code = Column(String(8))
    sector_small_code = Column(String(8))
    preferred_stock_code = Column(String(4))
    listing_date = Column(String(8))
    updated_at = Column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        UniqueConstraint("market", "ticker", name="uq_domestic_stock_master"),
        Index("ix_domestic_stock_master_name", "name"),
        Index("ix_domestic_stock_master_ticker", "ticker"),
    )
