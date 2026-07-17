from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import and_, func, or_
from sqlalchemy.orm import Session

from app.models.domestic_stock_master import DomesticStockMasterModel
from app.scrapers.kis.domestic_stock_master import DomesticStockMasterItem


_FIELDS = (
    "standard_code", "name", "sector_large_code", "sector_medium_code",
    "sector_small_code", "preferred_stock_code", "listing_date",
)


class DomesticStockMasterRepository:
    def upsert_items(self, db: Session, items: list[DomesticStockMasterItem]) -> int:
        generation = datetime.now(timezone.utc)
        affected = 0
        for item in items:
            row = db.query(DomesticStockMasterModel).filter_by(
                market=item.market, ticker=item.ticker
            ).first()
            values = {field: getattr(item, field) for field in _FIELDS}
            if row is None:
                db.add(DomesticStockMasterModel(
                    market=item.market, ticker=item.ticker,
                    updated_at=generation, **values,
                ))
                affected += 1
            else:
                if any(getattr(row, key) != value for key, value in values.items()):
                    for key, value in values.items():
                        setattr(row, key, value)
                    affected += 1
                row.updated_at = generation
        db.commit()
        return affected

    def find_candidates(self, db: Session, name_or_code: str) -> list[DomesticStockMasterModel]:
        normalized = name_or_code.strip()
        generations = dict(
            db.query(
                DomesticStockMasterModel.market,
                func.max(DomesticStockMasterModel.updated_at),
            ).group_by(DomesticStockMasterModel.market).all()
        )
        if not generations:
            return []
        current_generation = or_(*[
            and_(
                DomesticStockMasterModel.market == market,
                DomesticStockMasterModel.updated_at == updated_at,
            )
            for market, updated_at in generations.items()
        ])
        exact = db.query(DomesticStockMasterModel).filter(
            current_generation,
            (DomesticStockMasterModel.ticker == normalized)
            | (func.lower(DomesticStockMasterModel.name) == normalized.lower()),
        ).order_by(DomesticStockMasterModel.market, DomesticStockMasterModel.ticker).all()
        if exact:
            return exact
        return db.query(DomesticStockMasterModel).filter(
            current_generation,
            func.lower(DomesticStockMasterModel.name).contains(normalized.lower()),
        ).order_by(DomesticStockMasterModel.market, DomesticStockMasterModel.ticker).all()
