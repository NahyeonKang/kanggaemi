"""
app/models/domestic_derivative_master.py

국내 선물옵션 종목마스터(fo_idx_code_mts / fo_stk_code_mts) 적재 테이블.
품목(기초자산)별 후보 만기물 목록을 보관 → 활성월물 resolver가 여기서 후보를 추린다.
해외선물 overseas_future_master와 같은 사상(단일 마스터 테이블 + 소스 구분).
"""
from sqlalchemy import (
    BigInteger, Column, DateTime, Index, String, UniqueConstraint,
)

from app.db.base import Base


class DomesticDerivativeMasterModel(Base):
    __tablename__ = "domestic_derivative_master"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    market_type = Column(String(4), nullable=False)        # idx | stk
    srs_cd = Column(String(16), nullable=False)            # 단축코드(종목코드)
    std_cd = Column(String(24))                            # 표준코드
    product_type = Column(String(16))                      # 상품종류(선물/콜/풋 등)
    name = Column(String(64))                              # 한글종목명
    atm_div = Column(String(8))                            # ATM구분
    strike = Column(String(24))                            # 행사가(옵션)
    expiry_code = Column(String(16))                       # 월물구분코드
    underlying_cd = Column(String(16))                     # 기초자산 단축코드(품목)
    underlying_name = Column(String(64))                   # 기초자산 명
    updated_at = Column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        UniqueConstraint("market_type", "srs_cd", name="uq_domestic_deriv_master"),
        Index("ix_dom_deriv_underlying", "underlying_cd"),
        Index("ix_dom_deriv_product", "product_type"),
    )