from __future__ import annotations

import argparse
import logging
from pathlib import Path

from app.db.base import Base
from app.db.session import SessionLocal, engine
from app.models.domestic_stock_master import DomesticStockMasterModel
from app.repositories.domestic_stock_master_repository import DomesticStockMasterRepository
from app.scrapers.kis.domestic_stock_master import (
    _SPECS, download_domestic_stock_mst, parse_domestic_stock_mst,
)


logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def main() -> int:
    parser = argparse.ArgumentParser(description="Load KIS KOSPI/KOSDAQ stock masters.")
    parser.add_argument("--market", choices=["kospi", "kosdaq", "both"], default="both")
    parser.add_argument("--download", action="store_true")
    parser.add_argument("--dir", default="scripts/_master")
    args = parser.parse_args()
    markets = ["KOSPI", "KOSDAQ"] if args.market == "both" else [args.market.upper()]
    Base.metadata.create_all(bind=engine, tables=[DomesticStockMasterModel.__table__], checkfirst=True)
    repo = DomesticStockMasterRepository()
    with SessionLocal() as db:
        for market in markets:
            path = (
                download_domestic_stock_mst(market, args.dir)
                if args.download else Path(args.dir) / _SPECS[market]["mst"]
            )
            if not path.exists():
                raise FileNotFoundError(f"master not found: {path}; use --download")
            items = parse_domestic_stock_mst(path, market)
            affected = repo.upsert_items(db, items)
            logger.info("%s parsed=%d affected=%d", market, len(items), affected)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
