"""
app/repositories/exchange_rate_repository.py

Data access layer for exchange rate quotes.
All DB reads and writes go through this class.
"""
import logging
from datetime import datetime

from sqlalchemy.orm import Session

from app.models.exchange_rate import ExchangeRateQuoteModel
from app.schemas.exchange_rate import KBUsdKrwExchangeRate

logger = logging.getLogger(__name__)


class ExchangeRateRepository:
    """Repository for the exchange_rate_quotes table."""

    def upsert_quotes(self, db: Session, data: KBUsdKrwExchangeRate) -> int:
        """
        Insert or update intraday quotes from a KBUsdKrwExchangeRate result.

        Matches existing rows on (source, currency_code, target_date, quote_time).
        Updates base_rate and fetched_at if a row already exists; inserts otherwise.

        Returns:
            Number of rows inserted or updated.
        """
        source        = data.source
        currency_code = data.currency.split("/")[0]   # "USD/KRW" → "USD"
        target_date   = data.target_date or ""
        fetched_at    = (
            datetime.fromisoformat(data.fetched_at)
            if data.fetched_at
            else datetime.utcnow()
        )

        affected = 0
        for quote in data.quotes:
            existing = (
                db.query(ExchangeRateQuoteModel)
                .filter_by(
                    source=source,
                    currency_code=currency_code,
                    target_date=target_date,
                    quote_time=quote.quote_time,
                )
                .first()
            )
            if existing:
                existing.base_rate = quote.base_rate
                existing.fetched_at = fetched_at
            else:
                db.add(
                    ExchangeRateQuoteModel(
                        source=source,
                        currency_code=currency_code,
                        target_date=target_date,
                        quote_time=quote.quote_time,
                        base_rate=quote.base_rate,
                        fetched_at=fetched_at,
                    )
                )
            affected += 1

        db.commit()
        logger.info(
            "Upserted %d quotes for %s %s.", affected, currency_code, target_date
        )
        return affected

    def get_latest_quotes_by_date(
        self,
        db: Session,
        currency_code: str,
        target_date: str,
    ) -> list[ExchangeRateQuoteModel]:
        """
        Return all quotes for a given currency_code and target_date,
        ordered by quote_time descending (most recent first).
        """
        return (
            db.query(ExchangeRateQuoteModel)
            .filter_by(currency_code=currency_code, target_date=target_date)
            .order_by(ExchangeRateQuoteModel.quote_time.desc())
            .all()
        )
