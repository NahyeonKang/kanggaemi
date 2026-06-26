"""
app/services/yield_service.py

금리 도메인 비즈니스 로직 (resolution 분리):
  - yield_observation : FRED(US)/BOK(KR) daily 종가. monthly 추가 가능.
  - yield_intraday_snapshot : KIS 장중 스냅샷 (append-only).
"""
import logging
import re
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Optional

from sqlalchemy.orm import Session

from app.models.yield_rate import YieldObservationModel, YieldIntradaySnapshotModel
from app.repositories.yield_rate_repository import YieldRateRepository
from app.schemas.yield_rate import YieldSnapshotRecord
from app.scrapers.bok.bok_scraper import BOKScraper
from app.scrapers.fred.fred_scraper import FredScraper
from app.scrapers.kis.kis_scraper import KISScraper

logger = logging.getLogger(__name__)

_DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")

# (country, tenor) -> FRED series_id (US daily yields)
_FRED_SERIES_MAP: dict[tuple[str, str], str] = {
    ("US", "SOFR"): "SOFR",
    ("US", "2Y"): "DGS2",
    ("US", "10Y"): "DGS10",
    ("US", "30Y"): "DGS30",
}

# (country, tenor) -> BOK ECOS item_code (KR daily yields), stat 817Y002 / D
_BOK_STAT_CODE = "817Y002"
_BOK_PERIOD = "D"
_BOK_ITEM_CODE_MAP: dict[tuple[str, str], str] = {
    ("KR", "KOFR"): "010901000",
    ("KR", "3Y"): "010200000",
    ("KR", "10Y"): "010210000",
    ("KR", "30Y"): "010230000",
    ("KR", "CD91"): "010502000",
    ("KR", "CORP3Y_AA"): "010300000",
}

# KIS bcdt_code -> (country, tenor) (KR yield_intraday_snapshot)
_KIS_BCDT_CODE_MAP: dict[str, tuple[str, str]] = {
    "Y0101": ("KR", "3Y"),
    "Y0106": ("KR", "10Y"),
    "Y0117": ("KR", "30Y"),
    "Y0112": ("KR", "CD91"),
    "Y0102": ("KR", "CORP3Y_AA"),
}

_KIS_MARKET_DIV_CODE = "I"
_KIS_SCREEN_DIV_CODE = "20702"
_KIS_CLS_CODE = "0"


class YieldService:
    def __init__(self) -> None:
        self._repo = YieldRateRepository()

    # ── 관측 시계열 (daily) ──────────────────────────────────
    def sync_daily(self, db: Session, country: str, tenor: str) -> dict:
        self._validate_daily_tenor(country, tenor)
        key = (country, tenor)

        if key in _FRED_SERIES_MAP:
            source = "fred"
            data = FredScraper().fetch_last_1y_series(_FRED_SERIES_MAP[key])
            rows = [(o.observation_date, o.value) for o in data.observations]
        else:
            source = "bok"
            data = BOKScraper().fetch_last_1y_series(
                _BOK_STAT_CODE, _BOK_ITEM_CODE_MAP[key], _BOK_PERIOD
            )
            rows = [(o.observation_date, o.value) for o in data.observations]

        affected = self._repo.upsert_observations(db, source, country, tenor, "D", rows)
        dates = [d for d, _ in rows]
        return {
            "country": country,
            "tenor": tenor,
            "source": source,
            "resolution": "D",
            "affected_count": affected,
            "start_date": min(dates) if dates else None,
            "end_date": max(dates) if dates else None,
        }

    def sync_all_daily(self, db: Session) -> dict:
        results = [
            self.sync_daily(db, c, t)
            for c, t in [*_FRED_SERIES_MAP.keys(), *_BOK_ITEM_CODE_MAP.keys()]
        ]
        return {"results": results}

    def get_daily(
        self,
        db: Session,
        country: str,
        tenor: str,
        start_date: str,
        end_date: str,
    ) -> list[YieldObservationModel]:
        self._validate_daily_tenor(country, tenor)
        self._validate_date(start_date, "start_date")
        self._validate_date(end_date, "end_date")
        return self._repo.get_observations(db, country, tenor, "D", start_date, end_date)

    # ── 장중 스냅샷 (append-only) ────────────────────────────
    def sync_snapshots(self, db: Session) -> dict:
        """KIS comp-interest 1콜 → bcdt_code 필터링 → 매핑별 1행 append."""
        logger.info("Syncing yield_intraday_snapshot from KIS.")
        data = KISScraper().fetch_comp_interest(
            _KIS_MARKET_DIV_CODE, _KIS_SCREEN_DIV_CODE, _KIS_CLS_CODE,
        )
        observed_at = data.observed_at

        affected = 0
        tenors: list[str] = []
        for item in data.output1:
            key = _KIS_BCDT_CODE_MAP.get(item.bcdt_code)
            if key is None:
                continue
            country, tenor = key
            rec = YieldSnapshotRecord(
                source="kis",
                country=country,
                tenor=tenor,
                current_rate=self._to_decimal(item.bond_mnrt_prpr),
                prdy_vrss_sign=item.prdy_vrss_sign,
                prdy_vrss=self._to_decimal(item.bond_mnrt_prdy_vrss),
                prdy_ctrt=self._to_decimal(item.prdy_ctrt),
                base_date=item.stck_bsop_date,
                observed_at=observed_at,
            )
            affected += self._repo.insert_snapshot(db, rec)
            tenors.append(tenor)

        return {"source": "kis", "affected_count": affected, "tenors": tenors}

    def get_latest_snapshot(
        self, db: Session, country: str, tenor: str
    ) -> Optional[YieldIntradaySnapshotModel]:
        self._validate_snapshot_tenor(country, tenor)
        return self._repo.get_latest_snapshot(db, country, tenor)

    def get_snapshot_asof(
        self, db: Session, country: str, tenor: str, as_of: datetime
    ) -> Optional[YieldIntradaySnapshotModel]:
        self._validate_snapshot_tenor(country, tenor)
        return self._repo.get_snapshot_asof(db, country, tenor, as_of)

    def list_snapshots(
        self, db: Session, country: Optional[str] = None
    ) -> list[YieldIntradaySnapshotModel]:
        return self._repo.list_latest_snapshots(db, country)

    # ── validations ──────────────────────────────────────────
    @staticmethod
    def _validate_daily_tenor(country: str, tenor: str) -> None:
        key = (country, tenor)
        if key not in _FRED_SERIES_MAP and key not in _BOK_ITEM_CODE_MAP:
            allowed = sorted(_FRED_SERIES_MAP.keys() | _BOK_ITEM_CODE_MAP.keys())
            raise ValueError(f"Unknown (country, tenor) for yield_daily: {key!r}. Allowed: {allowed}")

    @staticmethod
    def _validate_snapshot_tenor(country: str, tenor: str) -> None:
        key = (country, tenor)
        if key not in _KIS_BCDT_CODE_MAP.values():
            allowed = sorted(set(_KIS_BCDT_CODE_MAP.values()))
            raise ValueError(f"Unknown (country, tenor) for snapshot: {key!r}. Allowed: {allowed}")

    @staticmethod
    def _validate_date(value: str, field_name: str) -> None:
        if not _DATE_PATTERN.match(value):
            raise ValueError(f"{field_name} must be YYYY-MM-DD, got: {value!r}")

    @staticmethod
    def _to_decimal(value: Optional[str]) -> Optional[Decimal]:
        if value is None or str(value).strip() == "":
            return None
        try:
            return Decimal(str(value).strip())
        except (InvalidOperation, ValueError):
            return None