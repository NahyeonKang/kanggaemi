"""
app/services/program_trade_service.py

프로그램매매 비즈니스 로직. 시장(market)/종목(stock) 라우팅 + 검증.
"""
import logging
import re
from typing import Optional

from sqlalchemy.orm import Session

from app.models.program_trade import ProgramTradeDailyModel
from app.repositories.program_trade_repository import ProgramTradeRepository
from app.scrapers.kis.kis_program_scraper import (
    KISProgramScraper, _TRADE_CLASSES, _ACCOUNT_TYPES,
)

logger = logging.getLogger(__name__)

_ALLOWED_MARKETS = frozenset({"KOSPI", "KOSDAQ"})
_ALLOWED_TRADE_CLASSES = frozenset(_TRADE_CLASSES)
_ALLOWED_ACCOUNT_TYPES = frozenset(_ACCOUNT_TYPES)
_DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_YYYYMMDD_PATTERN = re.compile(r"^\d{8}$")


class ProgramTradeService:
    def __init__(self) -> None:
        self._scraper = KISProgramScraper()
        self._repo = ProgramTradeRepository()

    # ── sync ─────────────────────────────────────────────────
    def sync_market_daily(
        self,
        db: Session,
        market: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> dict:
        self._validate_market(market)
        self._validate_yyyymmdd(start_date)
        self._validate_yyyymmdd(end_date)
        series = self._scraper.fetch_market_program_daily(
            market, start_date or "", end_date or "",
        )
        affected = self._repo.upsert_series(db, series)
        return self._sync_summary(series, affected)

    def sync_stock_daily(
        self,
        db: Session,
        ticker: str,
        date: Optional[str] = None,
    ) -> dict:
        self._validate_yyyymmdd(date)
        series = self._scraper.fetch_stock_program_daily(ticker, date or "")
        affected = self._repo.upsert_series(db, series)
        return self._sync_summary(series, affected)

    # ── get ──────────────────────────────────────────────────
    def get_market_trade(
        self,
        db: Session,
        market: str,
        start_date: str,
        end_date: str,
        trade_class: Optional[str] = None,
        account_type: Optional[str] = None,
    ) -> list[ProgramTradeDailyModel]:
        self._validate_market(market)
        self._validate_date(start_date, "start_date")
        self._validate_date(end_date, "end_date")
        self._validate_enum(trade_class, _ALLOWED_TRADE_CLASSES, "trade_class")
        self._validate_enum(account_type, _ALLOWED_ACCOUNT_TYPES, "account_type")
        return self._repo.get_series(
            db, scope="market", entity_code=market,
            start_date=start_date, end_date=end_date,
            trade_class=trade_class, account_type=account_type,
        )

    def get_stock_trade(
        self,
        db: Session,
        ticker: str,
        start_date: str,
        end_date: str,
    ) -> list[ProgramTradeDailyModel]:
        self._validate_date(start_date, "start_date")
        self._validate_date(end_date, "end_date")
        return self._repo.get_series(
            db, scope="stock", entity_code=ticker,
            start_date=start_date, end_date=end_date,
        )

    # ── helpers ──────────────────────────────────────────────
    @staticmethod
    def _sync_summary(series, affected: int) -> dict:
        dates = [o.observation_date for o in series.observations]
        return {
            "source": series.source,
            "scope": series.scope,
            "entity_code": series.entity_code,
            "affected_count": affected,
            "start_date": min(dates) if dates else None,
            "end_date": max(dates) if dates else None,
        }

    @staticmethod
    def _validate_market(market: str) -> None:
        if market not in _ALLOWED_MARKETS:
            raise ValueError(f"market must be one of {sorted(_ALLOWED_MARKETS)}, got: {market!r}")

    @staticmethod
    def _validate_enum(value: Optional[str], allowed: frozenset, name: str) -> None:
        if value is not None and value not in allowed:
            raise ValueError(f"{name} must be one of {sorted(allowed)}, got: {value!r}")

    @staticmethod
    def _validate_date(value: str, field_name: str) -> None:
        if not _DATE_PATTERN.match(value):
            raise ValueError(f"{field_name} must be YYYY-MM-DD, got: {value!r}")

    @staticmethod
    def _validate_yyyymmdd(value: Optional[str]) -> None:
        if value is not None and not _YYYYMMDD_PATTERN.match(value):
            raise ValueError(f"date must be YYYYMMDD, got: {value!r}")