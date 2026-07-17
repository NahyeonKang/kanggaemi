"""Create the universe-refresh storage tables idempotently.

The market-cap service owns ``market_cap_ranking`` but the repository has no
general migration framework yet, so this vertical-slice migration ensures both
the service prerequisite and the new point-in-time membership table.
"""

import logging
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.db.base import Base
from app.db.session import engine
from app.models.market_cap_ranking import MarketCapRankingModel
from app.models.universe_membership import UniverseMembershipModel


logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")


def create_tables() -> None:
    tables = [
        MarketCapRankingModel.__table__,
        UniverseMembershipModel.__table__,
    ]
    Base.metadata.create_all(
        bind=engine, tables=tables, checkfirst=True
    )
    logger = logging.getLogger(__name__)
    for table in tables:
        logger.info("Ensured table: %s", table.name)


def create_table() -> None:
    """Backward-compatible alias for the original single-table entry point."""
    create_tables()


if __name__ == "__main__":
    create_tables()
