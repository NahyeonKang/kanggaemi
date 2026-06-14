"""
app/services/yield_service.py

Business logic for the yield domain (interest rates), split by
time-resolution:
  - yield_daily    : official daily close yields, sourced from FRED (US) and
                      BOK (KR)
  - yield_snapshot : latest KIS comp-interest snapshot, one row per
                      (country, tenor), sourced from KIS

Source differences are confined to the scraper layer (FredScraper,
BOKScraper, KISScraper); this service routes by (country, tenor) and
validates inputs, raising ValueError on invalid input.
"""
import logging
import re
from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from app.models.yield_rate import YieldDailyModel, YieldSnapshotModel
from app.repositories.yield_rate_repository import YieldRateRepository
from app.schemas.yield_rate import YieldSnapshotRecord
from app.scrapers.bok.bok_scraper import BOKScraper
from app.scrapers.fred.fred_scraper import FredScraper
from app.scrapers.kis.kis_scraper import KISScraper

logger = logging.getLogger(__name__)

_DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")

# (country, tenor) -> FRED series_id, for US daily yields.
_FRED_SERIES_MAP: dict[tuple[str, str], str] = {
    ("US", "SOFR"): "SOFR",
    ("US", "2Y"): "DGS2",
    ("US", "10Y"): "DGS10",
    ("US", "30Y"): "DGS30",
}

# (country, tenor) -> BOK ECOS item_code, for KR daily yields.
# All series use stat_code 817Y002 (금리 종합), period "D" (daily).
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

# KIS comp-interest bcdt_code -> (country, tenor), for the KR yield_snapshot.
_KIS_BCDT_CODE_MAP: dict[str, tuple[str, str]] = {
    "Y0101": ("KR", "3Y"),          # 국고채 3년
    "Y0106": ("KR", "10Y"),         # 국고채 10년
    "Y0117": ("KR", "30Y"),         # 국고채 30년
    "Y0112": ("KR", "CD91"),        # CD (91일)
    "Y0102": ("KR", "CORP3Y_AA"),   # 회사채 무보증 3년AA-
}

_KIS_MARKET_DIV_CODE = "I"
_KIS_SCREEN_DIV_CODE = "20702"
_KIS_CLS_CODE = "1"


class YieldService:
    def __init__(self) -> None:
        self._repo = YieldRateRepository()

    # ------------------------------------------------------------------ #
    # yield_daily                                                          #
    # ------------------------------------------------------------------ #

    def sync_daily(self, db: Session, country: str, tenor: str) -> dict:
        self._validate_daily_tenor(country, tenor)
        key = (country, tenor)

        if key in _FRED_SERIES_MAP:
            series_id = _FRED_SERIES_MAP[key]
            source = "fred"
            logger.info("Syncing yield_daily %s/%s from FRED (%s).", country, tenor, series_id)
            data = FredScraper().fetch_last_1y_series(series_id)
            rows = [(obs.observation_date, obs.value) for obs in data.observations]
        else:
            item_code = _BOK_ITEM_CODE_MAP[key]
            source = "bok"
            logger.info("Syncing yield_daily %s/%s from BOK (%s).", country, tenor, item_code)
            data = BOKScraper().fetch_last_1y_series(_BOK_STAT_CODE, item_code, _BOK_PERIOD)
            rows = [(obs.observation_date, obs.value) for obs in data.observations]

        affected = self._repo.upsert_daily(db, country, tenor, source, rows)

        dates = [d for d, _ in rows]
        return {
            "country": country,
            "tenor": tenor,
            "source": source,
            "affected_count": affected,
            "start_date": min(dates) if dates else None,
            "end_date": max(dates) if dates else None,
        }

    def sync_all_daily(self, db: Session) -> dict:
        results = []
        for country, tenor in [*_FRED_SERIES_MAP.keys(), *_BOK_ITEM_CODE_MAP.keys()]:
            results.append(self.sync_daily(db, country, tenor))
        return {"results": results}

    def get_daily(
        self,
        db: Session,
        country: str,
        tenor: str,
        start_date: str,
        end_date: str,
    ) -> list[YieldDailyModel]:
        self._validate_daily_tenor(country, tenor)
        self._validate_date(start_date, "start_date")
        self._validate_date(end_date, "end_date")
        return self._repo.get_daily(db, country, tenor, start_date, end_date)

    # ------------------------------------------------------------------ #
    # yield_snapshot                                                       #
    # ------------------------------------------------------------------ #

    def sync_snapshots(self, db: Session) -> dict:
        """
        Refresh the yield_snapshot table from a single KIS comp-interest call.

        The KIS API has no per-tenor parameter: one call returns all bond
        types, which are filtered by bcdt_code and upserted individually.
        """
        logger.info("Syncing yield_snapshot from KIS (single comp-interest call).")

        data = KISScraper().fetch_comp_interest(
            _KIS_MARKET_DIV_CODE, _KIS_SCREEN_DIV_CODE, _KIS_CLS_CODE,
        )
        fetched_at = datetime.utcnow().isoformat()

        affected = 0
        tenors: list[str] = []
        for item in data.output1:
            key = _KIS_BCDT_CODE_MAP.get(item.bcdt_code)
            if key is None:
                continue
            country, tenor = key
            record = YieldSnapshotRecord(
                country=country,
                tenor=tenor,
                current_rate=self._to_float(item.bond_mnrt_prpr),
                prdy_vrss_sign=item.prdy_vrss_sign,
                prdy_vrss=self._to_float(item.bond_mnrt_prdy_vrss),
                prdy_ctrt=self._to_float(item.prdy_ctrt),
                base_date=item.stck_bsop_date,
                source="kis",
                fetched_at=fetched_at,
            )
            affected += self._repo.upsert_snapshot(db, record)
            tenors.append(tenor)

        return {"source": "kis", "affected_count": affected, "tenors": tenors}

    def get_snapshot(self, db: Session, country: str, tenor: str) -> Optional[YieldSnapshotModel]:
        self._validate_snapshot_tenor(country, tenor)
        return self._repo.get_snapshot(db, country, tenor)

    def list_snapshots(self, db: Session, country: Optional[str] = None) -> list[YieldSnapshotModel]:
        return self._repo.list_snapshots(db, country)

    # ------------------------------------------------------------------ #
    # Private helpers                                                      #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _validate_daily_tenor(country: str, tenor: str) -> None:
        key = (country, tenor)
        if key not in _FRED_SERIES_MAP and key not in _BOK_ITEM_CODE_MAP:
            allowed = sorted(_FRED_SERIES_MAP.keys() | _BOK_ITEM_CODE_MAP.keys())
            raise ValueError(
                f"Unknown (country, tenor) for yield_daily: {key!r}. "
                f"Allowed: {allowed}"
            )

    @staticmethod
    def _validate_snapshot_tenor(country: str, tenor: str) -> None:
        key = (country, tenor)
        if key not in _KIS_BCDT_CODE_MAP.values():
            allowed = sorted(set(_KIS_BCDT_CODE_MAP.values()))
            raise ValueError(
                f"Unknown (country, tenor) for yield_snapshot: {key!r}. "
                f"Allowed: {allowed}"
            )

    @staticmethod
    def _validate_date(value: str, field_name: str) -> None:
        if not _DATE_PATTERN.match(value):
            raise ValueError(f"{field_name} must be YYYY-MM-DD, got: {value!r}")

    @staticmethod
    def _to_float(value: Optional[str]) -> Optional[float]:
        try:
            return float(value)
        except (TypeError, ValueError):
            return None
