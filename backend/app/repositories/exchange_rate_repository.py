"""
app/repositories/exchange_rate_repository.py

Data access layer for exchange rate data.
"""
import logging
from datetime import datetime

from sqlalchemy.orm import Session

from app.models.exchange_rate import (
    ExchangeRateSummaryModel,
    ExchangeRateDailyModel,
)
from app.schemas.exchange_rate import (
    KBUsdKrwIntradaySummary,
    KBUsdKrwDailySeries,
)

logger = logging.getLogger(__name__)


def _parse_fetched_at(value: str | None) -> datetime:
    return datetime.fromisoformat(value) if value else datetime.utcnow()


class ExchangeRateRepository:
    """Repository for exchange rate summary and daily tables."""

    # ── 장중 요약 ────────────────────────────────────────────
    def upsert_summary(self, db: Session, data: KBUsdKrwIntradaySummary) -> int:
        """Insert or update one summary row. Returns affected row count (0 or 1)."""
        source = data.source
        currency_code = data.currency.split("/")[0]
        target_date = data.target_date
        fetched_at = _parse_fetched_at(data.fetched_at)

        existing = (
            db.query(ExchangeRateSummaryModel)
            .filter_by(
                source=source,
                currency_code=currency_code,
                target_date=target_date,
            )
            .first()
        )
        if existing:
            existing.first_rate = data.first_rate
            existing.last_rate = data.last_rate
            existing.daily_low = data.daily_low
            existing.daily_high = data.daily_high
            existing.daily_avg = data.daily_avg
            existing.fetched_at = fetched_at
        else:
            db.add(
                ExchangeRateSummaryModel(
                    source=source,
                    currency_code=currency_code,
                    target_date=target_date,
                    first_rate=data.first_rate,
                    last_rate=data.last_rate,
                    daily_low=data.daily_low,
                    daily_high=data.daily_high,
                    daily_avg=data.daily_avg,
                    fetched_at=fetched_at,
                )
            )

        db.commit()
        logger.info("Upserted summary for %s %s.", currency_code, target_date)
        return 1

    def get_summary_by_date(
        self, db: Session, currency_code: str, target_date: str
    ) -> ExchangeRateSummaryModel | None:
        """Return the summary row for a given currency and date, or None."""
        return (
            db.query(ExchangeRateSummaryModel)
            .filter_by(currency_code=currency_code, target_date=target_date)
            .first()
        )

    # ── 일별 종가 ────────────────────────────────────────────
    def upsert_daily_quotes(self, db: Session, data: KBUsdKrwDailySeries) -> int:
        """Insert or update daily rows. Returns affected row count."""
        source = data.source
        currency_code = data.currency.split("/")[0]
        fetched_at = _parse_fetched_at(data.fetched_at)

        affected = 0
        for quote in data.quotes:
            existing = (
                db.query(ExchangeRateDailyModel)
                .filter_by(
                    source=source,
                    currency_code=currency_code,
                    quote_date=quote.quote_date,
                )
                .first()
            )
            if existing:
                existing.base_rate = quote.base_rate
                existing.fetched_at = fetched_at
            else:
                db.add(
                    ExchangeRateDailyModel(
                        source=source,
                        currency_code=currency_code,
                        quote_date=quote.quote_date,
                        base_rate=quote.base_rate,
                        fetched_at=fetched_at,
                    )
                )
            affected += 1

        db.commit()
        logger.info(
            "Upserted %d daily quotes for %s.", affected, currency_code
        )
        return affected

    def get_daily_quotes(
        self,
        db: Session,
        currency_code: str,
        start_date: str,
        end_date: str,
    ) -> list[ExchangeRateDailyModel]:
        """Return daily rows within [start_date, end_date], oldest first."""
        return (
            db.query(ExchangeRateDailyModel)
            .filter(
                ExchangeRateDailyModel.currency_code == currency_code,
                ExchangeRateDailyModel.quote_date >= start_date,
                ExchangeRateDailyModel.quote_date <= end_date,
            )
            .order_by(ExchangeRateDailyModel.quote_date.asc())
            .all()
        )