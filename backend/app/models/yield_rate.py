"""
app/models/yield_rate.py

SQLAlchemy ORM models for the yield domain (interest rates), split by
time-resolution:
  - YieldDailyModel    : official daily close yields, sourced from FRED (US)
                          and BOK (KR). One row per (country, tenor, d).
  - YieldSnapshotModel : latest KIS comp-interest snapshot. One row per
                          (country, tenor).

Note: "yield" is a SQL reserved word, so the value columns are named
`close` / `current_rate` instead.
"""
from sqlalchemy import Column, DateTime, Float, String, func

from app.db.base import Base


class YieldDailyModel(Base):
    """Persisted official daily close yield observation (FRED / BOK)."""

    __tablename__ = "yield_daily"

    country     = Column(String(2),  primary_key=True)   # 'KR' / 'US'
    tenor       = Column(String(20), primary_key=True)   # '10Y','3Y','30Y','SOFR','2Y','KOFR','CD91','CORP3Y_AA'
    d           = Column(String(10), primary_key=True)   # YYYY-MM-DD
    close       = Column(Float,      nullable=True)
    source      = Column(String(10), nullable=False)     # 'fred' / 'bok'
    ingested_at = Column(DateTime,   nullable=False, server_default=func.now())

    def __repr__(self) -> str:
        return f"<YieldDailyModel {self.country} {self.tenor} {self.d} = {self.close}>"


class YieldSnapshotModel(Base):
    """Persisted latest KIS comp-interest snapshot, one row per (country, tenor)."""

    __tablename__ = "yield_snapshot"

    country        = Column(String(2),  primary_key=True)   # 'KR'
    tenor          = Column(String(20), primary_key=True)   # '3Y','10Y','30Y','CD91','CORP3Y_AA'
    current_rate   = Column(Float,      nullable=True)      # bond_mnrt_prpr (채권금리현재가)
    prdy_vrss_sign = Column(String(5),  nullable=True)       # 전일대비부호
    prdy_vrss      = Column(Float,      nullable=True)       # bond_mnrt_prdy_vrss (전일대비)
    prdy_ctrt      = Column(Float,      nullable=True)       # 전일대비율
    base_date      = Column(String(8),  nullable=True)       # stck_bsop_date (YYYYMMDD)
    source         = Column(String(10), nullable=False)      # 'kis'
    fetched_at     = Column(DateTime,   nullable=False)       # last update time

    def __repr__(self) -> str:
        return f"<YieldSnapshotModel {self.country} {self.tenor} = {self.current_rate}>"
