"""
app/models/investor_flow.py

투자자별 매매동향(일별) 수급 데이터 — long 테이블.

설계:
  - 투자자 유형(13~15종)을 컬럼이 아니라 행으로 풀어 wide 폭증 회피.
  - scope("market"|"stock") 하나로 시장·종목 수급을 통합.
      market scope: entity_code = 업종분류코드("0001"=전체), market = KOSPI/KOSDAQ
      stock  scope: entity_code = 6자리 티커,        market = 대표시장
  - resolution은 daily. exchange_rate_daily 패턴(upsert + ingested_at).
  - net_amount 단위: 백만원(종목 API 기준). net_qty 단위: 주(종목).
    시장 API 단위는 정의서에 명시 없음 — 원시값 저장, 필요 시 보정.

NOTE(정정): 수급은 당일 15:40 가집계 → 잠정→확정 정정이 잦음.
  잠정/확정 이력을 보존하려면 (..., observation_date, ingested_at) 유니크 +
  insert-on-change 버전 행으로 승격(point-in-time 재현의 핵심 케이스).
"""
from sqlalchemy import (
    BigInteger, Column, DateTime, Index, Numeric, String, UniqueConstraint,
)

from app.db.base import Base


class InvestorFlowDailyModel(Base):
    __tablename__ = "investor_flow_daily"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    source = Column(String(16), nullable=False)            # "kis"
    scope = Column(String(8), nullable=False)              # "market" | "stock"
    market = Column(String(8), nullable=False)             # "KOSPI" | "KOSDAQ"
    entity_code = Column(String(16), nullable=False)       # 업종코드 | 티커
    investor_type = Column(String(16), nullable=False)     # "frgn", "orgn", ...
    observation_date = Column(String(10), nullable=False)  # "YYYY-MM-DD"
    net_qty = Column(Numeric(24, 2))                       # 순매수 수량
    net_amount = Column(Numeric(24, 2))                    # 순매수 대금(백만원)
    ingested_at = Column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "source", "scope", "market", "entity_code",
            "investor_type", "observation_date",
            name="uq_investor_flow",
        ),
        Index(
            "ix_investor_flow_lookup",
            "scope", "market", "entity_code", "investor_type", "observation_date",
        ),
        # 종목은 티커가 전역 고유 → 시장 없이도 조회 가능하도록 보조 인덱스
        Index(
            "ix_investor_flow_stock",
            "scope", "entity_code", "investor_type", "observation_date",
        ),
    )