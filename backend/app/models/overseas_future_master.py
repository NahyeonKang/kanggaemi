"""
app/models/overseas_future_master.py

해외선물옵션 종목마스터(ffcode.mst) 적재 테이블.
sCalcDesz(계산 소수점) 등 시세 보정에 필요한 마스터 속성을 종목별로 보관.
resolver가 여기서 (exch_cd, srs_cd)→calc_decimal/currency를 조회한다.

currency는 ffcode.mst에 없음 → 별도 주입(수기/거래소 매핑). nullable.
"""
from sqlalchemy import (
    BigInteger, Column, DateTime, Index, Integer, String, UniqueConstraint,
)

from app.db.base import Base


class OverseasFutureMasterModel(Base):
    __tablename__ = "overseas_future_master"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    srs_cd = Column(String(32), nullable=False)            # 종목코드 (예: 6AM24)
    exch_cd = Column(String(16))                           # 거래소코드 (예: CME)
    product_code = Column(String(16))                      # 품목코드 (예: 6A)
    product_type = Column(String(8))                       # 품목종류
    name = Column(String(64))                              # 종목한글명
    disp_decimal = Column(Integer)                         # 출력 소수점
    calc_decimal = Column(Integer)                         # 계산 소수점(sCalcDesz)
    tick_size = Column(String(24))
    tick_value = Column(String(24))
    contract_size = Column(String(24))
    price_base = Column(String(8))                         # 가격표시진법
    mult = Column(String(16))                              # 환산승수
    sub_exch_cd = Column(String(8))
    currency = Column(String(8))                           # ffcode.mst 외부에서 주입
    updated_at = Column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        UniqueConstraint("srs_cd", name="uq_overseas_future_master"),
        Index("ix_ovf_master_product", "product_code"),
        Index("ix_ovf_master_exch", "exch_cd"),
    )