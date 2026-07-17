"""
app/services/instrument_price_service.py

통합 시세 비즈니스 로직. 한 sync로 OHLCV upsert + (자산군별) 스냅샷 append.
"""
import logging
import re
from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from app.models.instrument_price import (
    InstrumentOhlcvModel, StockValuationSnapshotModel, DerivativeSnapshotModel,
)
from app.repositories.instrument_price_repository import InstrumentPriceRepository
from app.repositories.overseas_future_master_repository import (
    OverseasFutureMasterRepository,
)
from app.scrapers.kis.kis_chart_scraper import KISChartScraper
from app.scrapers.kis.kis_overseas_futures_scraper import KISOverseasFuturesScraper

logger = logging.getLogger(__name__)

_ALLOWED_ASSET_CLASSES = frozenset({"stock", "index", "future", "option", "os_future"})
_ALLOWED_PERIODS = frozenset({"D", "W", "M", "Y"})
_DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_YYYYMMDD_PATTERN = re.compile(r"^\d{8}$")


class InstrumentPriceService:
    def __init__(self) -> None:
        self._scraper = KISChartScraper()
        self._overseas_scraper = KISOverseasFuturesScraper()
        self._repo = InstrumentPriceRepository()
        self._master_repo = OverseasFutureMasterRepository()

    def sync_chart(
        self,
        db: Session,
        asset_class: str,
        entity_code: str,
        period: str = "D",
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        adj: str = "0",
    ) -> dict:
        """한 호출 최대 100건. 더 길게는 날짜 윈도우 반복(업종·선물은 연속조회 지원)."""
        self._validate_asset_class(asset_class)
        self._validate_period(period)
        self._validate_yyyymmdd(start_date)
        self._validate_yyyymmdd(end_date)

        data = self._scraper.fetch_period_chart(
            asset_class, entity_code, period=period,
            start_date=start_date or "", end_date=end_date or "", adj=adj,
        )
        ohlcv_affected = self._repo.upsert_ohlcv(
            db, data.source, asset_class, entity_code, period, data.observations
        )

        snapshot_affected = 0
        if data.valuation is not None:
            snapshot_affected = self._repo.insert_valuation_snapshot(
                db, data.source, entity_code, data.valuation, data.observed_at
            )
        elif data.derivative is not None:
            snapshot_affected = self._repo.insert_derivative_snapshot(
                db, data.source, entity_code, data.derivative, data.observed_at
            )

        dates = [o.observation_date for o in data.observations]
        return {
            "source": data.source,
            "asset_class": asset_class,
            "entity_code": entity_code,
            "resolution": period,
            "ohlcv_affected": ohlcv_affected,
            "snapshot_affected": snapshot_affected,
            "start_date": min(dates) if dates else None,
            "end_date": max(dates) if dates else None,
        }

    def sync_overseas_futures(
        self,
        db: Session,
        exch_cd: str,
        srs_cd: str,
        close_date: str,                    # YYYYMMDD (조회종료일)
        qry_cnt: int = 40,
        calc_decimal: Optional[int] = None,  # sCalcDesz(마스터). None이면 raw
        currency: Optional[str] = None,      # 상품 통화(마스터)
        max_pages: int = 25,
    ) -> dict:
        """해외선물 일간 OHLCV. entity_code='EXCH:SRS', asset_class='os_future'.

        calc_decimal/currency 미지정 시 overseas_future_master에서 자동 조회.
        """
        self._validate_required_yyyymmdd(close_date, "close_date")

        # 마스터에서 sCalcDesz/currency 자동 보완 (명시값 우선)
        if calc_decimal is None:
            calc_decimal = self._master_repo.resolve_calc_decimal(db, srs_cd)
        if currency is None:
            currency = self._master_repo.resolve_currency(db, srs_cd)

        data = self._overseas_scraper.fetch_daily_ohlcv(
            exch_cd, srs_cd, close_date, qry_cnt=qry_cnt,
            calc_decimal=calc_decimal, currency=currency, max_pages=max_pages,
        )
        ohlcv_affected = self._repo.upsert_ohlcv(
            db, data.source, data.asset_class, data.entity_code, data.resolution,
            data.observations, currency=data.currency,
        )
        dates = [o.observation_date for o in data.observations]
        return {
            "source": data.source,
            "asset_class": data.asset_class,
            "entity_code": data.entity_code,
            "resolution": data.resolution,
            "ohlcv_affected": ohlcv_affected,
            "snapshot_affected": 0,
            "start_date": min(dates) if dates else None,
            "end_date": max(dates) if dates else None,
            "currency": data.currency,
        }

    def get_ohlcv(
        self, db: Session, asset_class: str, entity_code: str,
        resolution: str, start_date: str, end_date: str,
    ) -> list[InstrumentOhlcvModel]:
        self._validate_asset_class(asset_class)
        self._validate_period(resolution)
        self._validate_date(start_date, "start_date")
        self._validate_date(end_date, "end_date")
        return self._repo.get_ohlcv(db, asset_class, entity_code, resolution, start_date, end_date)

    def get_latest_valuation(self, db: Session, ticker: str) -> Optional[StockValuationSnapshotModel]:
        return self._repo.get_latest_valuation(db, ticker)

    def get_valuation_asof(self, db: Session, ticker: str, as_of: datetime) -> Optional[StockValuationSnapshotModel]:
        return self._repo.get_valuation_asof(db, ticker, as_of)

    def get_latest_derivative(self, db: Session, entity_code: str) -> Optional[DerivativeSnapshotModel]:
        return self._repo.get_latest_derivative(db, entity_code)

    def get_derivative_asof(self, db: Session, entity_code: str, as_of: datetime) -> Optional[DerivativeSnapshotModel]:
        return self._repo.get_derivative_asof(db, entity_code, as_of)

    # ── validations ──────────────────────────────────────────
    @staticmethod
    def _validate_asset_class(asset_class: str) -> None:
        if asset_class not in _ALLOWED_ASSET_CLASSES:
            raise ValueError(
                f"asset_class must be one of {sorted(_ALLOWED_ASSET_CLASSES)}, got: {asset_class!r}"
            )

    @staticmethod
    def _validate_period(period: str) -> None:
        if period not in _ALLOWED_PERIODS:
            raise ValueError(f"period must be one of {sorted(_ALLOWED_PERIODS)}, got: {period!r}")

    @staticmethod
    def _validate_date(value: str, field_name: str) -> None:
        if not _DATE_PATTERN.match(value):
            raise ValueError(f"{field_name} must be YYYY-MM-DD, got: {value!r}")

    @staticmethod
    def _validate_yyyymmdd(value: Optional[str]) -> None:
        if value is not None and not _YYYYMMDD_PATTERN.match(value):
            raise ValueError(f"date must be YYYYMMDD, got: {value!r}")

    @staticmethod
    def _validate_required_yyyymmdd(value: str, field_name: str) -> None:
        if not value or not _YYYYMMDD_PATTERN.match(value):
            raise ValueError(f"{field_name} must be YYYYMMDD, got: {value!r}")