"""
app/repositories/domestic_derivative_master_repository.py

국내 선물옵션 마스터 접근 계층.
  - upsert_items          : 파싱 결과 적재(값 변동 시 갱신). market_type 단위 교체 지원.
  - get_futures_candidates: 품목(기초자산)의 '선물' 후보 월물 목록 조회
                            → 활성월물 resolver가 이 후보들의 거래량을 비교.
"""
import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.models.domestic_derivative_master import DomesticDerivativeMasterModel
from app.scrapers.kis.domestic_derivative_master import DomesticDerivativeMasterItem

logger = logging.getLogger(__name__)

_FIELDS = (
    "std_cd", "product_type", "name", "atm_div", "strike",
    "expiry_code", "underlying_cd", "underlying_name",
)

# 상품종류에서 '선물'을 식별하는 힌트(옵션 제외). 실제 값은 마스터로 확인 필요.
_FUTURE_HINTS = ("선물", "future", "F")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class DomesticDerivativeMasterRepository:
    def upsert_items(
        self, db: Session, items: list[DomesticDerivativeMasterItem]
    ) -> int:
        now = _utcnow()
        affected = 0
        for it in items:
            if not it.srs_cd:
                continue
            existing = (
                db.query(DomesticDerivativeMasterModel)
                .filter_by(market_type=it.market_type, srs_cd=it.srs_cd)
                .first()
            )
            values = {f: getattr(it, f) for f in _FIELDS}
            if existing:
                if any(getattr(existing, k) != v for k, v in values.items()):
                    for k, v in values.items():
                        setattr(existing, k, v)
                    existing.updated_at = now
                    affected += 1
            else:
                db.add(DomesticDerivativeMasterModel(
                    market_type=it.market_type, srs_cd=it.srs_cd,
                    updated_at=now, **values,
                ))
                affected += 1
        db.commit()
        logger.info("Upserted %d domestic-derivative master rows.", affected)
        return affected

    def get_futures_candidates(
        self, db: Session, underlying_cd: str, market_type: str = "idx"
    ) -> list[DomesticDerivativeMasterModel]:
        """품목의 '선물' 종목만(옵션 제외) 반환. 월물 후보로 사용.

        product_type이 선물임을 나타내는 행만 필터. 실제 상품종류 값 체계는
        마스터로 확인 후 _FUTURE_HINTS를 조정할 것.
        """
        rows = (
            db.query(DomesticDerivativeMasterModel)
            .filter_by(market_type=market_type, underlying_cd=underlying_cd)
            .all()
        )
        return [r for r in rows if _is_future(r.product_type)]

    def get_by_srs(
        self, db: Session, market_type: str, srs_cd: str
    ) -> Optional[DomesticDerivativeMasterModel]:
        return (
            db.query(DomesticDerivativeMasterModel)
            .filter_by(market_type=market_type, srs_cd=srs_cd)
            .first()
        )


def _is_future(product_type: Optional[str]) -> bool:
    if not product_type:
        return False
    pt = product_type.strip().lower()
    return any(h.lower() in pt for h in _FUTURE_HINTS)