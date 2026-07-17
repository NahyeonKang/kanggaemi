from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo


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

