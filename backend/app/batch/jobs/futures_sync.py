from __future__ import annotations

import re

from app.batch.dates import normalize_yyyy_mm_dd, normalize_yyyymmdd
from app.batch.retry import run_targets
from app.batch.targets import selected_configured_targets
from app.batch.types import JobContext, JobResult, SkipTarget, TargetResult
from app.db.session import SessionLocal
from app.repositories.active_contract_repository import ActiveContractRepository
from app.services.instrument_price_service import InstrumentPriceService


def run_futures_sync(context: JobContext) -> JobResult:
    as_of_date = normalize_yyyy_mm_dd(context.date)
    close_date = as_of_date.replace("-", "")
    start_date = normalize_yyyymmdd(context.since)
    configured = _target_configs(context)
    targets = selected_configured_targets(context, configured)
    if start_date and start_date > close_date:
        raise ValueError("--since must be on or before --date")

    if context.dry_run:
        return JobResult(
            job_name=context.job_name,
            targets=[TargetResult(
                target=target, success=True, attempts=0,
                output={"dry_run": True, "as_of_date": as_of_date, **configured[target]},
            ) for target in targets],
        )

    service = InstrumentPriceService()
    _share_kis_auth(service)
    cache = ActiveContractRepository()

    def sync(target: str) -> dict:
        values = configured[target]
        with SessionLocal() as db:
            contract = cache.get_for_date(
                db, as_of_date, values["market"], values["product"]
            )
            if contract is None:
                raise RuntimeError(
                    f"active contract cache missing for {target} on {as_of_date}; "
                    "run active-contract-refresh first"
                )
            if values["market"] == "overseas":
                if not contract.exch_cd:
                    raise RuntimeError(f"exchange code missing in active contract cache for {target}")
                try:
                    return service.sync_overseas_futures(
                        db,
                        exch_cd=contract.exch_cd,
                        srs_cd=contract.contract_code,
                        close_date=close_date,
                        qry_cnt=int(context.config.get("overseas_qry_cnt", 40)),
                        max_pages=int(context.config.get("overseas_max_pages", 25)),
                    )
                except ValueError as exc:
                    error_code = _entitlement_error_code(
                        str(exc),
                        context.config.get("skip_entitlement_error_codes", []),
                        context.config.get("skip_entitlement_message_markers", []),
                    )
                    if error_code is None:
                        raise
                    raise SkipTarget(
                        "account_entitlement_required",
                        details={
                            "market": values["market"],
                            "product": values["product"],
                            "contract_code": contract.contract_code,
                            "exchange_code": contract.exch_cd,
                            "error_code": error_code,
                            "error_message": str(exc),
                        },
                    ) from exc
            return service.sync_chart(
                db,
                asset_class="future",
                entity_code=contract.contract_code,
                period=str(context.config.get("period", "D")),
                start_date=start_date,
                end_date=close_date,
                adj=str(context.config.get("adj", "0")),
            )

    return JobResult(
        job_name=context.job_name,
        targets=run_targets(context.job_name, targets, sync, context.retry_policy),
    )


def _target_configs(context: JobContext) -> dict[str, dict]:
    resolver_job = context.batch_config["jobs"][str(context.config["contract_job"])]
    configured: dict[str, dict] = {}
    for product in resolver_job["overseas"]:
        configured[f"overseas:{product}"] = {"market": "overseas", "product": product}
    for product in resolver_job["domestic"]:
        configured[f"domestic:{product}"] = {"market": "domestic", "product": product}
    return configured


def _entitlement_error_code(
    message: str,
    configured_codes: list[str],
    configured_markers: list[str],
) -> str | None:
    matched_code = next(
        (str(code) for code in configured_codes if str(code) in message), None
    )
    if matched_code is not None:
        return matched_code
    if not any(str(marker) in message for marker in configured_markers):
        return None
    parsed_code = re.search(r"\bEGW\d+\b", message)
    return parsed_code.group(0) if parsed_code else "KIS_SUB_EXCHANGE_ENTITLEMENT"


def _share_kis_auth(service: InstrumentPriceService) -> None:
    """Keep this two-scraper job to one KIS token without changing service code."""
    chart_scraper = getattr(service, "_scraper", None)
    overseas_scraper = getattr(service, "_overseas_scraper", None)
    overseas_auth = getattr(overseas_scraper, "_auth", None)
    if chart_scraper is not None and overseas_auth is not None:
        chart_scraper._auth = overseas_auth
