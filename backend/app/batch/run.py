from __future__ import annotations

import argparse
import logging
import os
import sys
from typing import Sequence

from app.batch.config import load_batch_config, retry_policy
from app.batch.lock import JobAlreadyRunningError, JobLock
from app.batch.logging import configure_json_logging
from app.batch.kis_token_throttle import KisTokenThrottle
from app.batch.registry import resolve_handler
from app.batch.types import JobContext
from app.db.session import engine


logger = logging.getLogger(__name__)
EXIT_SUCCESS = 0
EXIT_JOB_FAILED = 1
EXIT_USAGE_ERROR = 2
EXIT_ALREADY_RUNNING = 3


def _targets(values: list[str] | None) -> list[str] | None:
    if not values:
        return None
    parsed = [item.strip() for value in values for item in value.split(",") if item.strip()]
    return list(dict.fromkeys(parsed)) or None


def build_parser(job_names: Sequence[str]) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run one idempotent kanggaemi batch job.")
    parser.add_argument("job_name", choices=job_names)
    parser.add_argument("--targets", nargs="+", help="Space- or comma-separated target override.")
    parser.add_argument("--since", help="Backfill start date (YYYYMMDD or YYYY-MM-DD).")
    parser.add_argument("--date", help="Effective/end date (YYYYMMDD or YYYY-MM-DD).")
    parser.add_argument("--dry-run", action="store_true", help="Resolve work without external writes.")
    parser.add_argument("--config", help="Alternative batch jobs YAML path.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    configure_json_logging(os.getenv("BATCH_LOG_LEVEL", "INFO"))
    try:
        pre_parser = argparse.ArgumentParser(add_help=False)
        pre_parser.add_argument("--config")
        preliminary, _ = pre_parser.parse_known_args(argv)
        config = load_batch_config(preliminary.config)
        parser = build_parser(sorted(config["jobs"]))
        args = parser.parse_args(argv)
        job_config = config["jobs"][args.job_name]
        context = JobContext(
            job_name=args.job_name,
            config=job_config,
            batch_config=config,
            targets=_targets(args.targets),
            since=args.since,
            date=args.date,
            dry_run=args.dry_run,
            retry_policy=retry_policy(config, job_config),
        )
        handler = resolve_handler(str(job_config["handler"]))
        logger.info("job_started", extra={"event": "job_started", "job": args.job_name})
        if args.dry_run:
            result = handler(context)
        else:
            with JobLock(args.job_name, engine, os.getenv("BATCH_LOCK_DIR")):
                if bool(job_config.get("uses_kis", False)):
                    min_interval = float(
                        config.get("defaults", {}).get(
                            "kis_token_min_interval_seconds", 65
                        )
                    )
                    KisTokenThrottle().reserve(args.job_name, min_interval)
                result = handler(context)
        logger.info(
            "job_finished",
            extra={
                "event": "job_finished", "job": args.job_name, "success": result.success,
                "target_count": len(result.targets), "succeeded": result.succeeded,
                "skipped": result.skipped, "failed": result.failed,
            },
        )
        return EXIT_SUCCESS if result.success else EXIT_JOB_FAILED
    except JobAlreadyRunningError as exc:
        logger.error("job_lock_rejected", extra={"event": "job_lock_rejected", "error": str(exc)})
        return EXIT_ALREADY_RUNNING
    except (ValueError, KeyError, OSError) as exc:
        logger.error("job_configuration_failed", extra={"event": "job_configuration_failed", "error": str(exc)})
        return EXIT_USAGE_ERROR
    except Exception as exc:
        logger.exception("job_failed", extra={"event": "job_failed", "error": str(exc)})
        return EXIT_JOB_FAILED


if __name__ == "__main__":
    sys.exit(main())
