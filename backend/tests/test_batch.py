from __future__ import annotations

import json
import logging

import pytest

from app.batch.config import load_batch_config
from app.batch.dates import normalize_yyyy_mm_dd, normalize_yyyymmdd
from app.batch.logging import JsonFormatter
from app.batch.retry import run_target
from app.batch.run import _targets
from app.batch.types import RetryPolicy


def test_config_declares_vertical_slice_jobs():
    jobs = load_batch_config()["jobs"]
    assert jobs["universe-refresh"]["markets"]["kospi"]["top_n"] == 10
    assert jobs["universe-refresh"]["markets"]["kosdaq"]["top_n"] == 10
    assert jobs["universe-refresh"]["div_cls_code"] == "1"
    assert jobs["stock-prices"]["depends_on"] == ["universe-refresh"]


def test_target_retry_succeeds_without_stopping_process():
    attempts = 0

    def operation():
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise RuntimeError("temporary")
        return {"ok": True}

    result = run_target(
        "sample", "005930", operation,
        RetryPolicy(max_attempts=3, initial_delay_seconds=0),
        sleep=lambda _: None,
        jitter=lambda: 0,
    )
    assert result.success is True
    assert result.attempts == 3


def test_target_retry_reports_final_failure():
    result = run_target(
        "sample", "bad", lambda: (_ for _ in ()).throw(ValueError("broken")),
        RetryPolicy(max_attempts=2, initial_delay_seconds=0),
        sleep=lambda _: None,
        jitter=lambda: 0,
    )
    assert result.success is False
    assert result.attempts == 2
    assert result.error == "ValueError: broken"


@pytest.mark.parametrize(
    ("raw", "hyphenated", "compact"),
    [("20260718", "2026-07-18", "20260718"), ("2026-07-18", "2026-07-18", "20260718")],
)
def test_date_normalization(raw, hyphenated, compact):
    assert normalize_yyyy_mm_dd(raw) == hyphenated
    assert normalize_yyyymmdd(raw) == compact


def test_target_parser_accepts_spaces_and_commas():
    assert _targets(["005930,000660", "005930"]) == ["005930", "000660"]


def test_json_formatter_emits_context():
    record = logging.LogRecord("batch", logging.INFO, __file__, 1, "done", (), None)
    record.job = "stock-prices"
    payload = json.loads(JsonFormatter().format(record))
    assert payload["message"] == "done"
    assert payload["job"] == "stock-prices"
    assert payload["timestamp"].endswith("+00:00")


def test_all_targets_are_attempted_when_one_fails():
    from app.batch.retry import run_targets

    visited = []

    def operation(target):
        visited.append(target)
        if target == "bad":
            raise RuntimeError("nope")
        return target

    results = run_targets(
        "sample", ["good-1", "bad", "good-2"], operation,
        RetryPolicy(max_attempts=1, initial_delay_seconds=0),
    )
    assert visited == ["good-1", "bad", "good-2"]
    assert [result.success for result in results] == [True, False, True]


def test_latest_complete_membership_ignores_newer_partial_snapshot():
    from datetime import datetime, timezone

    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    from app.models.universe_membership import UniverseMembershipModel
    from app.repositories.universe_membership_repository import UniverseMembershipRepository

    test_engine = create_engine("sqlite:///:memory:")
    UniverseMembershipModel.__table__.create(test_engine)
    now = datetime.now(timezone.utc)
    rows = [
        UniverseMembershipModel(id=1, univ_date="2026-07-13", market="kospi", ticker="A", rank=1, ingested_at=now),
        UniverseMembershipModel(id=2, univ_date="2026-07-13", market="kosdaq", ticker="B", rank=1, ingested_at=now),
        UniverseMembershipModel(id=3, univ_date="2026-07-20", market="kospi", ticker="C", rank=1, ingested_at=now),
    ]
    with Session(test_engine) as db:
        db.add_all(rows)
        db.commit()
        tickers = UniverseMembershipRepository().get_latest_tickers(
            db, {"kospi": 1, "kosdaq": 1}
        )
    assert tickers == ["B", "A"]


def test_file_lock_rejects_same_job(tmp_path):
    from sqlalchemy import create_engine

    from app.batch.lock import JobAlreadyRunningError, JobLock

    test_engine = create_engine("sqlite:///:memory:")
    with JobLock("same-job", test_engine, str(tmp_path)):
        with pytest.raises(JobAlreadyRunningError):
            with JobLock("same-job", test_engine, str(tmp_path)):
                pass
