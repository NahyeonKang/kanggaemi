"""
app/services/domestic_bond_rate_service.py

Business logic for KIS domestic bond interest rate data: fetching,
persistence, and retrieval.
"""
import logging
import re
from typing import Optional

from sqlalchemy.orm import Session

from app.models.domestic_bond_rate import DomesticBondRateModel
from app.repositories.domestic_bond_rate_repository import DomesticBondRateRepository
from app.schemas.domestic_bond_rate import DomesticBondRateData, DomesticBondRateRecord
from app.scrapers.kis.kis_domestic_bond_rate_scraper import KISDomesticBondRateScraper

logger = logging.getLogger(__name__)

_DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_KIS_DATE_PATTERN = re.compile(r"^\d{8}$")


class DomesticBondRateService:
    def __init__(self) -> None:
        self._scraper = KISDomesticBondRateScraper()
        self._repo = DomesticBondRateRepository()

    def sync_domestic_bond_rates(
        self,
        db: Session,
        fid_cond_mrkt_div_code: str,
        fid_cond_scr_div_code: str,
        fid_div_cls_code: str,
        fid_div_cls_code1: str = "",
    ) -> dict:
        self._validate_required(fid_cond_mrkt_div_code, "fid_cond_mrkt_div_code")
        self._validate_required(fid_cond_scr_div_code, "fid_cond_scr_div_code")
        self._validate_required(fid_div_cls_code, "fid_div_cls_code")

        logger.info(
            "Syncing domestic bond rates (mrkt=%s, scr=%s, cls=%s, cls1=%s).",
            fid_cond_mrkt_div_code, fid_cond_scr_div_code, fid_div_cls_code, fid_div_cls_code1,
        )

        data = self._scraper.fetch_comp_interest(
            fid_cond_mrkt_div_code,
            fid_cond_scr_div_code,
            fid_div_cls_code,
            fid_div_cls_code1,
        )

        records = [self._to_record(data, item) for item in (data.output1 + data.output2)]
        affected = self._repo.upsert_rates(db, records)

        return {
            "source": data.source,
            "market_div_code": data.market_div_code,
            "screen_div_code": data.screen_div_code,
            "cls_code": data.cls_code,
            "affected_count": affected,
        }

    def get_rates(
        self,
        db: Session,
        market_div_code: str,
        base_date: Optional[str] = None,
    ) -> list[DomesticBondRateModel]:
        self._validate_required(market_div_code, "market_div_code")
        if base_date is not None:
            self._validate_date(base_date, "base_date")
        return self._repo.get_rates(db, market_div_code, base_date)

    # ------------------------------------------------------------------ #
    # Private helpers                                                      #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _to_record(data: DomesticBondRateData, item) -> DomesticBondRateRecord:
        return DomesticBondRateRecord(
            source=data.source,
            market_div_code=data.market_div_code,
            screen_div_code=data.screen_div_code,
            cls_code=data.cls_code,
            rate_code=item.bcdt_code,
            rate_name=item.hts_kor_isnm,
            rate_value=DomesticBondRateService._to_float(item.bond_mnrt_prpr),
            base_date=DomesticBondRateService._normalize_date(item.stck_bsop_date),
            fetched_at=data.fetched_at,
        )

    @staticmethod
    def _to_float(value: str) -> Optional[float]:
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _normalize_date(value: str) -> str:
        """KIS stck_bsop_date (YYYYMMDD) → YYYY-MM-DD."""
        if _KIS_DATE_PATTERN.match(value):
            return f"{value[:4]}-{value[4:6]}-{value[6:]}"
        return value

    @staticmethod
    def _validate_required(value: str, field_name: str) -> None:
        if not value:
            raise ValueError(f"{field_name} is required.")

    @staticmethod
    def _validate_date(value: str, field_name: str) -> None:
        if not _DATE_PATTERN.match(value):
            raise ValueError(f"{field_name} must be YYYY-MM-DD, got: {value!r}")
