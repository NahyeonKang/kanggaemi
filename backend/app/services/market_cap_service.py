"""
app/services/market_cap_service.py

시총상위 비즈니스 로직. 유니버스 생성이 이 서비스를 소비한다
(get_top_tickers로 시장별 상위 N 티커를 얻어 universe_membership 구성).
"""
import logging
import re
from datetime import datetime
from typing import Optional
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.models.market_cap_ranking import MarketCapRankingModel
from app.repositories.market_cap_ranking_repository import MarketCapRankingRepository
from app.scrapers.kis.kis_market_cap_scraper import KISMarketCapScraper, _MARKET_CODE

logger = logging.getLogger(__name__)

_KST = ZoneInfo("Asia/Seoul")
_ALLOWED_MARKETS = frozenset(_MARKET_CODE)
_ALLOWED_DIV_CLS = frozenset({"0", "1", "2"})
_DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class MarketCapService:
    def __init__(self) -> None:
        self._scraper = KISMarketCapScraper()
        self._repo = MarketCapRankingRepository()

    def sync_market_cap(
        self,
        db: Session,
        market: str = "kospi",
        div_cls_code: str = "0",
        top_n: Optional[int] = None,
        date: Optional[str] = None,     # YYYY-MM-DD, 생략 시 오늘(KST)
    ) -> dict:
        self._validate_market(market)
        self._validate_div_cls(div_cls_code)
        if date is not None:
            self._validate_date(date, "date")

        obs_date = date or datetime.now(_KST).strftime("%Y-%m-%d")
        ranking = self._scraper.fetch_market_cap_ranking(market, div_cls_code, top_n)
        affected = self._repo.upsert_ranking(db, ranking, obs_date)
        ranks = [r.rank for r in ranking.rows]
        return {
            "source": ranking.source,
            "market": market,
            "observation_date": obs_date,
            "affected_count": affected,
            "top_rank": max(ranks) if ranks else None,
        }

    def get_market_cap(
        self, db: Session, market: str, observation_date: str,
        top_n: Optional[int] = None,
    ) -> list[MarketCapRankingModel]:
        self._validate_market(market)
        self._validate_date(observation_date, "observation_date")
        return self._repo.get_ranking(db, market, observation_date, top_n)

    def get_top_tickers(
        self, db: Session, market: str, top_n: int,
        observation_date: Optional[str] = None,
    ) -> list[str]:
        """유니버스용: 시장별 상위 N 티커. date 미지정 시 최신 스냅샷."""
        self._validate_market(market)
        obs_date = observation_date or self._repo.latest_date(db, market)
        if obs_date is None:
            return []
        rows = self._repo.get_ranking(db, market, obs_date, top_n)
        return [r.ticker for r in rows]

    # ── validations ──────────────────────────────────────────
    @staticmethod
    def _validate_market(market: str) -> None:
        if market not in _ALLOWED_MARKETS:
            raise ValueError(f"market must be one of {sorted(_ALLOWED_MARKETS)}, got: {market!r}")

    @staticmethod
    def _validate_div_cls(value: str) -> None:
        if value not in _ALLOWED_DIV_CLS:
            raise ValueError(f"div_cls_code must be one of {sorted(_ALLOWED_DIV_CLS)} (0전체/1보통주/2우선주), got: {value!r}")

    @staticmethod
    def _validate_date(value: str, field_name: str) -> None:
        if not _DATE_PATTERN.match(value):
            raise ValueError(f"{field_name} must be YYYY-MM-DD, got: {value!r}")