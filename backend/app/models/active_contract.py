"""Daily point-in-time cache of resolved futures contracts."""

from sqlalchemy import BigInteger, Column, DateTime, Index, Integer, Numeric, String, UniqueConstraint

from app.db.base import Base


class ActiveContractModel(Base):
    __tablename__ = "active_contract"

    id = Column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    as_of_date = Column(String(10), nullable=False)       # YYYY-MM-DD, KST
    market = Column(String(16), nullable=False)           # overseas | domestic
    product = Column(String(32), nullable=False)          # WTI | KOSPI200
    contract_code = Column(String(32), nullable=False)    # srs_cd
    exch_cd = Column(String(16))
    master_product_code = Column(String(16))
    expiry_date = Column(String(10))
    resolution_method = Column(String(24), nullable=False)  # master_flag | volume
    reference_date = Column(String(10))
    reference_volume = Column(Numeric(24, 2))
    rollover_reason = Column(String(32))
    resolved_at = Column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        UniqueConstraint("as_of_date", "market", "product", name="uq_active_contract_daily"),
        Index("ix_active_contract_latest", "market", "product", "as_of_date"),
    )
