"""
app/models/stock_financials.py

개별 종목 재무(financials) — 4개 KIS 재무 API를 결산기간(stac_yymm) 기준으로 병합.
grain: (ticker, period_type, stac_yymm). period_type = annual(0) | quarter(1).

수집 항목(요청 필드):
  재무비율[080]   : 매출액증가율/영업이익증가율/순이익증가율/ROE/EPS
  수익성비율[081] : 매출액순이익율
  기타주요비율[082]: EV_EBITDA
  손익계산서[079] : 매출액/영업이익

단위: 금액(매출/영업이익) 억원, EPS 원, 증가율/ROE/마진 %, EV_EBITDA 배수.
NOTE: 분기(quarter) 데이터는 '연단위 누적합산'(YTD). 개별 분기값 아님(정의서 명시).
NOTE(EPS 이관): 종전 stock_valuation_snapshot의 eps는 제거, 여기 eps로 대체.
"""
from sqlalchemy import (
    BigInteger, Column, DateTime, Index, Numeric, String, UniqueConstraint,
)

from app.db.base import Base


class StockFinancialsModel(Base):
    __tablename__ = "stock_financials"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    source = Column(String(16), nullable=False)            # "kis"
    ticker = Column(String(12), nullable=False)            # 6자리 종목코드
    period_type = Column(String(8), nullable=False)        # "annual" | "quarter"
    stac_yymm = Column(String(6), nullable=False)          # 결산년월 "YYYYMM"

    # 재무비율[080]
    revenue_growth = Column(Numeric(14, 4))                # 매출액 증가율(%)
    op_income_growth = Column(Numeric(14, 4))              # 영업이익 증가율(%)
    net_income_growth = Column(Numeric(14, 4))             # 순이익 증가율(%)
    roe = Column(Numeric(12, 4))                           # ROE(%)
    eps = Column(Numeric(18, 4))                           # EPS(원)
    # 수익성비율[081]
    net_profit_margin = Column(Numeric(12, 4))             # 매출액 순이익율(%)
    # 기타주요비율[082]
    ev_ebitda = Column(Numeric(14, 4))                     # EV/EBITDA(배)
    # 손익계산서[079]
    revenue = Column(Numeric(20, 2))                       # 매출액(억원, 누적)
    op_income = Column(Numeric(20, 2))                     # 영업이익(억원, 누적)

    ingested_at = Column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        UniqueConstraint("source", "ticker", "period_type", "stac_yymm",
                         name="uq_stock_financials"),
        Index("ix_stock_financials_lookup", "ticker", "period_type", "stac_yymm"),
    )