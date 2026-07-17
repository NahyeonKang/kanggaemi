from __future__ import annotations

import os
import hashlib
import tempfile
from contextlib import contextmanager
from datetime import date
from pathlib import Path
from typing import BinaryIO, Iterator

import yaml
from sqlalchemy.orm import Session

from app.agent.catalog import CORE_DIR, class_policy
from app.agent.contracts import AssetExtraction, ClassificationResult
from app.agent.llm import AssetExtractor
from app.repositories.domestic_stock_master_repository import DomesticStockMasterRepository


class AssetTaxonomyRegistry:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or CORE_DIR / "asset_taxonomy.yaml"

    def find(self, value: str) -> dict | None:
        needle = _normalized(value)
        for asset in self._assets():
            if asset.get("status", "active") != "active":
                continue
            candidates = [asset["asset_code"], asset["asset_name"], *asset.get("aliases", [])]
            if any(_normalized(str(candidate)) == needle for candidate in candidates):
                return asset
        return None

    def append(self, asset: dict) -> None:
        digest = hashlib.sha256(str(self.path.resolve()).encode()).hexdigest()[:16]
        lock_path = (
            Path(tempfile.gettempdir()) / "kanggaemi-agent-locks"
            / f"asset-taxonomy-{digest}.lock"
        )
        with _locked_file(lock_path):
            if self.find(str(asset["asset_code"])) or self.find(str(asset["asset_name"])):
                return
            dumped = yaml.safe_dump(
                [asset], allow_unicode=True, sort_keys=False, default_flow_style=False
            ).rstrip()
            block = "\n\n" + "\n".join(f"  {line}" for line in dumped.splitlines()) + "\n"
            with self.path.open("a", encoding="utf-8") as file:
                file.write(block)
                file.flush()
                os.fsync(file.fileno())

    def _assets(self) -> list[dict]:
        with self.path.open(encoding="utf-8") as file:
            data = yaml.safe_load(file)
        return list(data.get("assets", []))


class AssetResolver:
    def __init__(
        self,
        extractor: AssetExtractor,
        registry: AssetTaxonomyRegistry | None = None,
        master_repository: DomesticStockMasterRepository | None = None,
    ) -> None:
        self.extractor = extractor
        self.registry = registry or AssetTaxonomyRegistry()
        self.master = master_repository or DomesticStockMasterRepository()

    def resolve(self, db: Session, user_query: str) -> ClassificationResult:
        extracted = self.extractor.extract(user_query)
        cached = self.registry.find(extracted.asset_name)
        if cached is not None:
            return self._classification(cached, extracted, cache_hit=True)

        policy = class_policy(extracted.asset_class)
        if extracted.asset_class != "kr_equity":
            raise ValueError(
                f"cache miss grounding is not implemented for {extracted.asset_class}; "
                "no entity code was generated"
            )
        candidates = self.master.find_candidates(db, extracted.asset_name)
        if not candidates:
            raise ValueError(
                f"ASSET_NOT_FOUND: {extracted.asset_name!r} is absent from domestic_stock_master"
            )
        chosen = candidates[0]
        aliases = list(dict.fromkeys([
            chosen.name, chosen.ticker, *extracted.aliases,
        ]))
        asset = {
            "asset_code": chosen.ticker,
            "asset_name": chosen.name,
            "asset_class": "kr_equity",
            "region": policy["region"],
            "market": chosen.market,
            "sector": chosen.sector_large_code,
            "aliases": aliases,
            "resolved_by": "llm+korean_investment_master",
            "verified_at": date.today().isoformat(),
            "expires_at": None,
            "status": "active",
        }
        self.registry.append(asset)
        result = self._classification(asset, extracted, cache_hit=False)
        if len(candidates) > 1:
            result.ambiguity = {
                "candidates": [
                    {"asset_code": row.ticker, "asset_name": row.name, "market": row.market}
                    for row in candidates
                ],
                "selected_by": "exact-name-then-market-order",
            }
            result.classification_confidence = min(result.classification_confidence, 0.6)
        return result

    @staticmethod
    def _classification(
        asset: dict, extracted: AssetExtraction, *, cache_hit: bool
    ) -> ClassificationResult:
        policy = class_policy(asset["asset_class"])
        return ClassificationResult(
            asset_code=str(asset["asset_code"]),
            asset_name=str(asset["asset_name"]),
            asset_class=str(asset["asset_class"]),
            region=str(asset.get("region") or policy["region"]),
            market=str(asset.get("market") or ""),
            sector=asset.get("sector"),
            currency="KRW" if policy["region"] == "kr" else None,
            aliases=list(asset.get("aliases", [])),
            horizon=extracted.horizon or policy["default_horizon"],
            query_intent=extracted.query_intent,
            applicable_dimensions=list(policy["applicable_dimensions"]),
            classification_confidence=extracted.confidence,
            cache_hit=cache_hit,
        )


def _normalized(value: str) -> str:
    return "".join(value.casefold().split())


@contextmanager
def _locked_file(path: Path) -> Iterator[None]:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+b") as lock:
        _ensure_byte(lock)
        lock.seek(0)
        if os.name == "nt":
            import msvcrt

            msvcrt.locking(lock.fileno(), msvcrt.LK_LOCK, 1)
        else:
            import fcntl

            fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            lock.seek(0)
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(lock.fileno(), fcntl.LOCK_UN)


def _ensure_byte(file: BinaryIO) -> None:
    file.seek(0, os.SEEK_END)
    if file.tell() == 0:
        file.write(b"0")
        file.flush()
