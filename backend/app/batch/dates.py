from __future__ import annotations

from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

import holidays


KST = ZoneInfo("Asia/Seoul")


def normalize_yyyy_mm_dd(value: str | None) -> str:
    if value is None:
        return datetime.now(KST).strftime("%Y-%m-%d")
    for fmt in ("%Y%m%d", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, fmt).strftime("%Y-%m-%d")
        except ValueError:
            pass
    raise ValueError(f"date must be YYYYMMDD or YYYY-MM-DD, got: {value!r}")


def normalize_yyyymmdd(value: str | None) -> str | None:
    if value is None:
        return None
    return normalize_yyyy_mm_dd(value).replace("-", "")


def latest_completed_kr_business_date(now: datetime | None = None) -> str:
    """Latest KR business date whose 15:40 stock flow data is complete."""
    current = now.astimezone(KST) if now is not None else datetime.now(KST)
    kr_holidays = holidays.KR()

    def is_business_day(value) -> bool:
        return value.weekday() < 5 and value not in kr_holidays

    candidate = current.date()
    if not is_business_day(candidate) or current.time() < time(15, 40):
        candidate -= timedelta(days=1)
    while not is_business_day(candidate):
        candidate -= timedelta(days=1)
    return candidate.strftime("%Y%m%d")
