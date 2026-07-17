"""
app/repositories/overseas_future_master_repository.py

해외선물 마스터 접근 계층.
  - upsert_items    : ffcode.mst 파싱 결과 적재(값 변동 시 갱신).
  - get_by_srs      : 종목코드로 단건 조회.
  - resolve_calc_decimal : 종목코드 → sCalcDesz. 없으면 품목코드 fallback.
  - resolve_currency     : 종목코드 → currency(주입돼 있으면).
"""
import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models.overseas_future_master import OverseasFutureMasterModel
from app.scrapers.kis.overseas_future_master import OverseasFutureMasterItem

logger = logging.getLogger(__name__)

_FIELDS = (
    "exch_cd", "product_code", "product_type", "name", "disp_decimal",
    "calc_decimal", "tick_size", "tick_value", "contract_size",
    "price_base", "mult", "most_active_flag", "nearest_flag",
    "spread_flag", "spread_leg1_flag", "sub_exch_cd",
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class OverseasFutureMasterRepository:
    def upsert_items(
        self,
        db: Session,
        items: list[OverseasFutureMasterItem],
        currency_map: Optional[dict[str, str]] = None,
    ) -> int:
        """currency_map: {srs_cd 또는 exch_cd: currency} 선택 주입."""
        now = _utcnow()
        # A disappeared contract must not retain last week's active flags.
        (
            db.query(OverseasFutureMasterModel)
            .filter(
                or_(
                    OverseasFutureMasterModel.most_active_flag == "1",
                    OverseasFutureMasterModel.nearest_flag == "1",
                )
            )
            .update(
                {
                    OverseasFutureMasterModel.most_active_flag: None,
                    OverseasFutureMasterModel.nearest_flag: None,
                    OverseasFutureMasterModel.updated_at: now,
                },
                synchronize_session=False,
            )
        )
        affected = 0
        for it in items:
            if not it.srs_cd:
                continue
            currency = None
            if currency_map:
                currency = currency_map.get(it.srs_cd) or currency_map.get(it.exch_cd or "")
            existing = (
                db.query(OverseasFutureMasterModel)
                .filter_by(srs_cd=it.srs_cd)
                .first()
            )
            values = {f: getattr(it, f) for f in _FIELDS}
            if currency is not None:
                values["currency"] = currency

            if existing:
                changed = any(getattr(existing, k) != v for k, v in values.items())
                if changed:
                    for k, v in values.items():
                        setattr(existing, k, v)
                    affected += 1
                # updated_at is also the full-master load generation marker.
                existing.updated_at = now
            else:
                db.add(OverseasFutureMasterModel(srs_cd=it.srs_cd, updated_at=now, **values))
                affected += 1
        db.commit()
        logger.info("Upserted %d overseas-future master rows.", affected)
        return affected

    def get_by_srs(self, db: Session, srs_cd: str) -> Optional[OverseasFutureMasterModel]:
        return (
            db.query(OverseasFutureMasterModel)
            .filter_by(srs_cd=srs_cd)
            .first()
        )

    def resolve_calc_decimal(self, db: Session, srs_cd: str) -> Optional[int]:
        row = self.get_by_srs(db, srs_cd)
        if row is not None and row.calc_decimal is not None:
            return row.calc_decimal
        # 종목 미등록 시: 품목코드(선두 영문) 기준 fallback
        prefix = _product_prefix(srs_cd)
        if prefix:
            alt = (
                db.query(OverseasFutureMasterModel)
                .filter_by(product_code=prefix)
                .filter(OverseasFutureMasterModel.calc_decimal.isnot(None))
                .first()
            )
            if alt is not None:
                return alt.calc_decimal
        return None

    def resolve_currency(self, db: Session, srs_cd: str) -> Optional[str]:
        row = self.get_by_srs(db, srs_cd)
        return row.currency if row is not None else None

    def resolve_active_contract(
        self, db: Session, product_code: str
    ) -> Optional[OverseasFutureMasterModel]:
        """Resolve an outright contract: most-active first, nearest as fallback."""
        rows = (
            db.query(OverseasFutureMasterModel)
            .filter_by(product_code=product_code)
            .all()
        )
        if rows:
            latest_generation = max(row.updated_at for row in rows)
            rows = [row for row in rows if row.updated_at == latest_generation]
        outright = [row for row in rows if "-" not in row.srs_cd]
        most_active = sorted(
            (row for row in outright if row.most_active_flag == "1"),
            key=lambda row: row.srs_cd,
        )
        if len(most_active) > 1:
            raise RuntimeError(
                f"multiple most-active contracts for {product_code}: "
                f"{[row.srs_cd for row in most_active]}"
            )
        if most_active:
            return most_active[0]
        nearest = sorted(
            (row for row in outright if row.nearest_flag == "1"),
            key=lambda row: row.srs_cd,
        )
        if len(nearest) > 1:
            raise RuntimeError(
                f"multiple nearest contracts for {product_code}: "
                f"{[row.srs_cd for row in nearest]}"
            )
        return nearest[0] if nearest else None


def _product_prefix(srs_cd: str) -> Optional[str]:
    """'6AM24' → '6A' (선두 영숫자 품목 추정). 만기(월물) 코드 제거용 휴리스틱."""
    if not srs_cd:
        return None
    # 뒤쪽 월물 패턴(영문월+2자리연도)을 떼는 단순 휴리스틱
    import re
    m = re.match(r"^([0-9A-Z]+?)[FGHJKMNQUVXZ]\d{1,2}$", srs_cd)
    return m.group(1) if m else None
