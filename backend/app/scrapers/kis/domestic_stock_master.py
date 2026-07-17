from __future__ import annotations

import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path


_SPECS = {
    "KOSPI": {
        "mst": "kospi_code.mst", "zip": "kospi_code.mst.zip", "tail": 227,
        "url": "https://new.real.download.dws.co.kr/common/master/kospi_code.mst.zip",
        "widths": [
            2, 1, 4, 4, 4, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1,
            1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 9, 5, 5, 1, 1,
            1, 2, 1, 1, 1, 2, 2, 2, 3, 1, 3, 12, 12, 8, 15, 21, 2,
            7, 1, 1, 1, 1, 1, 9, 9, 9, 5, 9, 8, 9, 3, 1, 1, 1,
        ],
        "listing_idx": 49, "preferred_idx": 54,
    },
    "KOSDAQ": {
        "mst": "kosdaq_code.mst", "zip": "kosdaq_code.mst.zip", "tail": 221,
        "url": "https://new.real.download.dws.co.kr/common/master/kosdaq_code.mst.zip",
        "widths": [
            2, 1, 4, 4, 4, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1,
            1, 1, 1, 1, 1, 1, 1, 1, 9, 5, 5, 1, 1, 1, 2, 1, 1, 1,
            2, 2, 2, 3, 1, 3, 12, 12, 8, 15, 21, 2, 7, 1, 1, 1, 1,
            9, 9, 9, 5, 9, 8, 9, 3, 1, 1, 1,
        ],
        "listing_idx": 44, "preferred_idx": 49,
    },
}


@dataclass(frozen=True)
class DomesticStockMasterItem:
    market: str
    ticker: str
    standard_code: str | None
    name: str
    sector_large_code: str | None
    sector_medium_code: str | None
    sector_small_code: str | None
    preferred_stock_code: str | None
    listing_date: str | None


def download_domestic_stock_mst(market: str, directory: str | Path) -> Path:
    spec = _SPECS[market.upper()]
    target_dir = Path(directory)
    target_dir.mkdir(parents=True, exist_ok=True)
    archive = target_dir / spec["zip"]
    urllib.request.urlretrieve(spec["url"], archive)
    with zipfile.ZipFile(archive) as zipped:
        member = next((name for name in zipped.namelist() if name.endswith(spec["mst"])), None)
        if member is None:
            raise ValueError(f"{spec['mst']} not found in {archive}")
        with zipped.open(member) as source, (target_dir / spec["mst"]).open("wb") as output:
            output.write(source.read())
    archive.unlink(missing_ok=True)
    return target_dir / spec["mst"]


def parse_domestic_stock_mst(
    path: str | Path, market: str
) -> list[DomesticStockMasterItem]:
    market = market.upper()
    spec = _SPECS[market]
    items: list[DomesticStockMasterItem] = []
    with Path(path).open(encoding="cp949") as file:
        for raw in file:
            row = raw.rstrip("\r\n")
            if len(row) <= spec["tail"]:
                continue
            prefix, tail = row[:-spec["tail"]], row[-spec["tail"]:]
            ticker = prefix[:9].strip()
            name = prefix[21:].strip()
            if not ticker or not name:
                continue
            values = _split_fixed_width(tail, spec["widths"])
            items.append(DomesticStockMasterItem(
                market=market,
                ticker=ticker,
                standard_code=prefix[9:21].strip() or None,
                name=name,
                sector_large_code=values[2] or None,
                sector_medium_code=values[3] or None,
                sector_small_code=values[4] or None,
                preferred_stock_code=values[spec["preferred_idx"]] or None,
                listing_date=values[spec["listing_idx"]] or None,
            ))
    return items


def _split_fixed_width(value: str, widths: list[int]) -> list[str]:
    fields: list[str] = []
    offset = 0
    for width in widths:
        fields.append(value[offset:offset + width].strip())
        offset += width
    if offset != len(value):
        raise ValueError(f"master tail length mismatch: expected={offset}, actual={len(value)}")
    return fields
