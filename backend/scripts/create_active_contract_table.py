"""Create step-5 resolver storage and add ffcode flag columns idempotently."""

import logging

from sqlalchemy import inspect, text

from app.db.base import Base
from app.db.session import engine
from app.models.active_contract import ActiveContractModel
from app.models.domestic_derivative_master import DomesticDerivativeMasterModel
from app.models.overseas_future_master import OverseasFutureMasterModel


logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

_FLAG_COLUMNS = {
    "most_active_flag": "VARCHAR(1)",
    "nearest_flag": "VARCHAR(1)",
    "spread_flag": "VARCHAR(1)",
    "spread_leg1_flag": "VARCHAR(1)",
}


def create_tables() -> None:
    master_tables = [
        OverseasFutureMasterModel.__table__,
        DomesticDerivativeMasterModel.__table__,
    ]
    Base.metadata.create_all(bind=engine, tables=master_tables, checkfirst=True)

    columns = {
        column["name"] for column in inspect(engine).get_columns("overseas_future_master")
    }
    with engine.begin() as connection:
        for name, sql_type in _FLAG_COLUMNS.items():
            if name not in columns:
                connection.execute(
                    text(f"ALTER TABLE overseas_future_master ADD COLUMN {name} {sql_type}")
                )
                logger.info("Added column: overseas_future_master.%s", name)

    Base.metadata.create_all(
        bind=engine, tables=[ActiveContractModel.__table__], checkfirst=True
    )
    logger.info("Ensured table: active_contract")


if __name__ == "__main__":
    create_tables()
