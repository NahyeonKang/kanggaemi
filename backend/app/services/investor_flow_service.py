"""
app/services/investor_flow_service.py

수급 비즈니스 로직. 시장(market)/종목(stock) 라우팅 + 검증.
소스 차이는 스크래퍼 계층에 한정.
"""
import logging
import re
from typing import Optional

from sqlalchemy.orm import Session

from app.models.investor_flow import InvestorFlowDailyModel
from app.repositories.investor_flow_repository import InvestorFlowRepository
from app.scrapers.kis.kis_investor_scraper import KISInvestorScraper, INVESTOR_FIELDS

logger = logging.getLogger(__name__)

_ALLOWED_MARKETS = frozenset({"KOSPI", "KOSDAQ"})
_ALLOWED_INVESTOR_TYPES = frozenset(INVESTOR_FIELDS.keys())
_DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_YYYYMMDD_PATTERN = re.compile(r"^\d{8}$")


class InvestorFlowService:
    def __init__(self) -> None:
        self._scraper = KISInvestorScraper()
        self._repo = InvestorFlowRepository()

    # ── sync ─────────────────────────────────────────────────
    def sync_market_daily(
        self,
        db: Session,
        market: str,
        sector_code: str = "0001",
        date: Optional[str] = None,
    ) -> dict:
        self._validate_market(market)
        self._validate_yyyymmdd(date)
        series = self._scraper.fetch_market_investor_daily(market, sector_code, date)
        affected = self._repo.upsert_flows(db, series)
        return self._sync_summary(series, affected)

    def sync_stock_daily(
        self,
        db: Session,
        ticker: str,
        date: Optional[str] = None,
    ) -> dict:
        self._validate_yyyymmdd(date)
        series = self._scraper.fetch_stock_investor_daily(ticker, date)
        affected = self._repo.upsert_flows(db, series)
        return self._sync_summary(series, affected)

    # ── get ──────────────────────────────────────────────────
    def get_market_flow(
        self,
        db: Session,
        market: str,
        start_date: str,
        end_date: str,
        investor_type: Optional[str] = None,
        sector_code: str = "0001",
    ) -> list[InvestorFlowDailyModel]:
        self._validate_market(market)
        self._validate_date(start_date, "start_date")
        self._validate_date(end_date, "end_date")
        self._validate_investor_type(investor_type)
        return self._repo.get_flows(
            db, scope="market", entity_code=sector_code,
            start_date=start_date, end_date=end_date,
            investor_type=investor_type, market=market,
        )

    def get_stock_flow(
        self,
        db: Session,
        ticker: str,
        start_date: str,
        end_date: str,
        investor_type: Optional[str] = None,
    ) -> list[InvestorFlowDailyModel]:
        self._validate_date(start_date, "start_date")
        self._validate_date(end_date, "end_date")
        self._validate_investor_type(investor_type)
        return self._repo.get_flows(
            db, scope="stock", entity_code=ticker,
            start_date=start_date, end_date=end_date,
            investor_type=investor_type, market=None,
        )

    # ── helpers ──────────────────────────────────────────────
    @staticmethod
    def _sync_summary(series, affected: int) -> dict:
        dates = [o.observation_date for o in series.observations]
        return {
            "source": series.source,
            "scope": series.scope,
            "market": series.market,
            "entity_code": series.entity_code,
            "affected_count": affected,
            "investor_types": sorted(_ALLOWED_INVESTOR_TYPES),
            "start_date": min(dates) if dates else None,
            "end_date": max(dates) if dates else None,
        }

    @staticmethod
    def _validate_market(market: str) -> None:
        if market not in _ALLOWED_MARKETS:
            raise ValueError(f"market must be one of {sorted(_ALLOWED_MARKETS)}, got: {market!r}")

    @staticmethod
    def _validate_investor_type(investor_type: Optional[str]) -> None:
        if investor_type is not None and investor_type not in _ALLOWED_INVESTOR_TYPES:
            raise ValueError(
                f"investor_type must be one of {sorted(_ALLOWED_INVESTOR_TYPES)}, got: {investor_type!r}"
            )

    @staticmethod
    def _validate_date(value: str, field_name: str) -> None:
        if not _DATE_PATTERN.match(value):
            raise ValueError(f"{field_name} must be YYYY-MM-DD, got: {value!r}")

    @staticmethod
    def _validate_yyyymmdd(value: Optional[str]) -> None:
        if value is not None and not _YYYYMMDD_PATTERN.match(value):
            raise ValueError(f"date must be YYYYMMDD, got: {value!r}")