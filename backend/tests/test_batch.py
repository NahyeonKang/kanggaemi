from __future__ import annotations

import json
import logging

import pytest

from app.batch.config import load_batch_config, retry_policy
from app.batch.dates import normalize_yyyy_mm_dd, normalize_yyyymmdd
from app.batch.logging import JsonFormatter
from app.batch.retry import run_target
from app.batch.run import _targets
from app.batch.types import RetryPolicy


def test_config_declares_vertical_slice_jobs():
    config = load_batch_config()
    jobs = config["jobs"]
    assert jobs["universe-refresh"]["markets"]["kospi"]["top_n"] == 10
    assert jobs["universe-refresh"]["markets"]["kosdaq"]["top_n"] == 10
    assert jobs["universe-refresh"]["div_cls_code"] == "1"
    assert jobs["stock-prices"]["depends_on"] == ["universe-refresh"]
    policy = retry_policy(config, jobs["stock-prices"])
    assert policy.initial_delay_seconds == 65
    assert policy.multiplier == 2
    assert policy.max_delay_seconds == 130
    assert policy.jitter_fraction == 0


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


def test_known_target_skip_is_not_retried_or_counted_as_failure():
    from app.batch.types import JobResult, SkipTarget

    sleeps = []
    result = run_target(
        "sample", "paid-target",
        lambda: (_ for _ in ()).throw(SkipTarget(
            "account_entitlement_required",
            details={"error_code": "EGW00551", "contract_code": "BZU26"},
        )),
        RetryPolicy(max_attempts=3, initial_delay_seconds=65),
        sleep=sleeps.append,
    )
    job = JobResult(job_name="sample", targets=[result])
    assert result.skipped is True
    assert result.attempts == 1
    assert result.output["contract_code"] == "BZU26"
    assert sleeps == []
    assert job.success is True
    assert job.succeeded == 0
    assert job.skipped == 1
    assert job.failed == 0


@pytest.mark.parametrize(
    ("raw", "hyphenated", "compact"),
    [("20260718", "2026-07-18", "20260718"), ("2026-07-18", "2026-07-18", "20260718")],
)
def test_date_normalization(raw, hyphenated, compact):
    assert normalize_yyyy_mm_dd(raw) == hyphenated
    assert normalize_yyyymmdd(raw) == compact


def test_latest_completed_stock_flow_date_uses_previous_business_day_before_cutoff():
    from datetime import datetime

    from app.batch.dates import KST, latest_completed_kr_business_date

    assert latest_completed_kr_business_date(
        datetime(2026, 7, 18, 5, 0, tzinfo=KST)
    ) == "20260717"
    assert latest_completed_kr_business_date(
        datetime(2026, 7, 17, 15, 39, tzinfo=KST)
    ) == "20260716"
    assert latest_completed_kr_business_date(
        datetime(2026, 7, 17, 15, 40, tzinfo=KST)
    ) == "20260717"


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


def test_kis_token_throttle_waits_before_second_process_slot(tmp_path):
    from app.batch.kis_token_throttle import KisTokenThrottle

    now = [100.0]
    waits = []

    def clock():
        return now[0]

    def sleep(seconds):
        waits.append(seconds)
        now[0] += seconds

    throttle = KisTokenThrottle(str(tmp_path))
    assert throttle.reserve("first", 65, clock=clock, sleep=sleep) == 0
    assert throttle.reserve("second", 65, clock=clock, sleep=sleep) == 65
    assert waits == [65]


def test_futures_sync_reuses_one_auth_client_for_both_scrapers():
    from types import SimpleNamespace

    from app.batch.jobs.futures_sync import _share_kis_auth

    shared_auth = object()
    service = SimpleNamespace(
        _scraper=SimpleNamespace(_auth=object()),
        _overseas_scraper=SimpleNamespace(_auth=shared_auth),
    )
    _share_kis_auth(service)
    assert service._scraper._auth is shared_auth


def test_ffcode_tail_flags_are_parsed_from_documented_offsets():
    from app.scrapers.kis.overseas_future_master import _parse_row

    chars = [" "] * 223
    chars[0:6] = list("GCQ26 ")
    chars[-7:] = list("0101N53")
    item = _parse_row("".join(chars))
    assert item.most_active_flag == "0"
    assert item.nearest_flag == "1"
    assert item.spread_flag == "0"
    assert item.spread_leg1_flag == "1"
    assert item.sub_exch_cd == "N53"


def test_domestic_expiry_is_second_thursday_and_type_one_is_future():
    from datetime import date

    from app.batch.resolvers.domestic import _expiry_date
    from app.repositories.domestic_derivative_master_repository import _is_future

    assert _is_future("1") is True
    assert _expiry_date("F 202609") == date(2026, 9, 10)


def test_active_contract_config_contains_all_requested_products():
    from app.batch.jobs.active_contracts import _target_configs

    config = load_batch_config()["jobs"]["active-contract-refresh"]
    targets = _target_configs(config)
    assert set(targets) == {
        "overseas:WTI", "overseas:BRENT", "overseas:GOLD",
        "overseas:COPPER", "overseas:NATURALGAS", "domestic:KOSPI200",
    }
    assert targets["overseas:WTI"]["product_code"] == "WBS"
    assert targets["domestic:KOSPI200"]["rollover_business_days"] == 3


def test_overseas_master_prefers_most_active_from_latest_generation():
    from datetime import datetime, timedelta, timezone

    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    from app.models.overseas_future_master import OverseasFutureMasterModel
    from app.repositories.overseas_future_master_repository import OverseasFutureMasterRepository

    test_engine = create_engine("sqlite:///:memory:")
    OverseasFutureMasterModel.__table__.create(test_engine)
    now = datetime.now(timezone.utc)
    with Session(test_engine) as db:
        db.add_all([
            OverseasFutureMasterModel(
                id=1, srs_cd="GCOLD", product_code="GC", nearest_flag="1",
                updated_at=now - timedelta(days=7),
            ),
            OverseasFutureMasterModel(
                id=2, srs_cd="GCQ26", product_code="GC", nearest_flag="1",
                updated_at=now,
            ),
            OverseasFutureMasterModel(
                id=3, srs_cd="GCM26", product_code="GC", most_active_flag="1",
                updated_at=now,
            ),
        ])
        db.commit()
        resolved = OverseasFutureMasterRepository().resolve_active_contract(db, "GC")
    assert resolved.srs_cd == "GCM26"


def test_domestic_resolver_uses_latest_common_date_volume(monkeypatch):
    from datetime import datetime, timezone
    from decimal import Decimal
    from types import SimpleNamespace

    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    import app.batch.resolvers.domestic as resolver
    from app.models.domestic_derivative_master import DomesticDerivativeMasterModel

    test_engine = create_engine("sqlite:///:memory:")
    DomesticDerivativeMasterModel.__table__.create(test_engine)
    now = datetime.now(timezone.utc)
    with Session(test_engine) as db:
        db.add_all([
            DomesticDerivativeMasterModel(
                id=1, market_type="idx", srs_cd="A01609", product_type="1",
                name="F 202609", underlying_cd="2001", updated_at=now,
            ),
            DomesticDerivativeMasterModel(
                id=2, market_type="idx", srs_cd="A01612", product_type="1",
                name="F 202612", underlying_cd="2001", updated_at=now,
            ),
        ])
        db.commit()

        class FakeCache:
            saved = None

            def get_for_date(self, *_):
                return None

            def get_latest_before(self, *_):
                return None

            def upsert_daily(self, _db, **values):
                FakeCache.saved = values
                return SimpleNamespace(**values)

        class FakeService:
            def sync_chart(self, *_args, **_kwargs):
                return {}

            def get_ohlcv(self, _db, _asset, code, *_args):
                volume = Decimal("100") if code == "A01609" else Decimal("250")
                return [SimpleNamespace(observation_date="2026-07-17", volume=volume)]

        monkeypatch.setattr(resolver, "ActiveContractRepository", FakeCache)
        monkeypatch.setattr(resolver, "InstrumentPriceService", FakeService)
        result = resolver.resolve_domestic_contract(
            db,
            as_of_date="2026-07-18",
            product="KOSPI200",
            underlying_cd="2001",
            market_type="idx",
            candidate_count=3,
            lookback_days=14,
            rollover_business_days=3,
        )
    assert result["contract_code"] == "A01612"
    assert result["reference_date"] == "2026-07-17"
    assert FakeCache.saved["reference_volume"] == Decimal("250")


def test_stage_six_and_seven_targets_are_declarative():
    from app.batch.jobs.futures_sync import _target_configs
    from app.batch.types import JobContext, RetryPolicy

    config = load_batch_config()["jobs"]
    assert config["futures-sync"]["depends_on"] == ["active-contract-refresh"]
    context = JobContext(
        job_name="futures-sync", config=config["futures-sync"],
        batch_config={"jobs": config}, targets=None, since=None, date=None,
        dry_run=True, retry_policy=RetryPolicy(),
    )
    assert set(_target_configs(context)) == {
        "overseas:WTI", "overseas:BRENT", "overseas:GOLD",
        "overseas:COPPER", "overseas:NATURALGAS", "domestic:KOSPI200",
    }
    assert config["market-indices"]["targets"]["VKOSPI"]["entity_code"] == "0503"
    assert config["market-indices"]["targets"]["VKOSPI"] == {"entity_code": "0503"}
    assert config["stock-financials"]["div_cls_codes"] == ["0", "1"]
    assert config["stock-investor-flow"]["target_source"] == "latest_universe_membership"


def test_futures_sync_uses_exact_daily_cache(monkeypatch):
    from types import SimpleNamespace

    import app.batch.jobs.futures_sync as job
    from app.batch.types import JobContext, RetryPolicy

    calls = []

    class FakeSession:
        def __enter__(self): return self
        def __exit__(self, *_): return None

    class FakeCache:
        def get_for_date(self, _db, as_of_date, market, product):
            calls.append(("cache", as_of_date, market, product))
            return SimpleNamespace(contract_code="GCQ26", exch_cd="CME")

    class FakeService:
        def sync_overseas_futures(self, _db, **kwargs):
            calls.append(("sync", kwargs))
            return kwargs

    monkeypatch.setattr(job, "SessionLocal", FakeSession)
    monkeypatch.setattr(job, "ActiveContractRepository", FakeCache)
    monkeypatch.setattr(job, "InstrumentPriceService", FakeService)
    config = load_batch_config()
    context = JobContext(
        job_name="futures-sync", config=config["jobs"]["futures-sync"],
        batch_config=config, targets=["overseas:GOLD"], since=None,
        date="20260718", dry_run=False, retry_policy=RetryPolicy(max_attempts=1),
    )
    result = job.run_futures_sync(context)
    assert result.success
    assert calls[0] == ("cache", "2026-07-18", "overseas", "GOLD")
    assert calls[1][1]["srs_cd"] == "GCQ26"
    assert calls[1][1]["close_date"] == "20260718"


def test_futures_sync_reports_missing_cache_without_calling_service(monkeypatch):
    import app.batch.jobs.futures_sync as job
    from app.batch.types import JobContext, RetryPolicy

    class FakeSession:
        def __enter__(self): return self
        def __exit__(self, *_): return None

    class FakeCache:
        def get_for_date(self, *_): return None

    class FakeService:
        def sync_overseas_futures(self, *_args, **_kwargs):
            raise AssertionError("must not collect without cache")

    monkeypatch.setattr(job, "SessionLocal", FakeSession)
    monkeypatch.setattr(job, "ActiveContractRepository", FakeCache)
    monkeypatch.setattr(job, "InstrumentPriceService", FakeService)
    config = load_batch_config()
    context = JobContext(
        job_name="futures-sync", config=config["jobs"]["futures-sync"],
        batch_config=config, targets=["overseas:WTI"], since=None,
        date="20260718", dry_run=False, retry_policy=RetryPolicy(max_attempts=1),
    )
    result = job.run_futures_sync(context)
    assert not result.success
    assert "active contract cache missing" in result.targets[0].error


def test_futures_sync_skips_known_account_entitlement_error(monkeypatch):
    from types import SimpleNamespace

    import app.batch.jobs.futures_sync as job
    from app.batch.types import JobContext, RetryPolicy

    class FakeSession:
        def __enter__(self): return self
        def __exit__(self, *_): return None

    class FakeCache:
        def get_for_date(self, *_):
            return SimpleNamespace(contract_code="BZU26", exch_cd="CME")

    class FakeService:
        calls = 0

        def sync_overseas_futures(self, *_args, **_kwargs):
            FakeService.calls += 1
            raise ValueError(
                'KIS overseas-futures call failed (CME:BZU26): 500 - '
                '{msg1:"NYMEX SUB거래소 신청 계좌가 아닙니다.",msg_cd:"EGW00551"}'
            )

    monkeypatch.setattr(job, "SessionLocal", FakeSession)
    monkeypatch.setattr(job, "ActiveContractRepository", FakeCache)
    monkeypatch.setattr(job, "InstrumentPriceService", FakeService)
    config = load_batch_config()
    context = JobContext(
        job_name="futures-sync", config=config["jobs"]["futures-sync"],
        batch_config=config, targets=["overseas:BRENT"], since=None,
        date="20260718", dry_run=False, retry_policy=RetryPolicy(max_attempts=3),
    )
    result = job.run_futures_sync(context)
    target = result.targets[0]
    assert result.success is True
    assert target.skipped is True
    assert target.attempts == 1
    assert target.output["product"] == "BRENT"
    assert target.output["contract_code"] == "BZU26"
    assert target.output["error_code"] == "EGW00551"
    assert FakeService.calls == 1


def test_entitlement_message_marker_catches_new_sub_exchange_code():
    from app.batch.jobs.futures_sync import _entitlement_error_code

    message = (
        'KIS overseas-futures call failed: '
        '{msg1:"COMEX SUB거래소 신청 계좌가 아닙니다.",msg_cd:"EGW00999"}'
    )
    assert _entitlement_error_code(
        message,
        configured_codes=["EGW00551", "EGW00553"],
        configured_markers=["SUB거래소 신청 계좌가 아닙니다"],
    ) == "EGW00999"


def test_market_index_dry_run_contains_vkospi_as_index():
    from app.batch.jobs.market_level import run_market_level
    from app.batch.types import JobContext, RetryPolicy

    config = load_batch_config()
    context = JobContext(
        job_name="market-indices", config=config["jobs"]["market-indices"],
        batch_config=config, targets=["VKOSPI"], since="20260101",
        date="20260718", dry_run=True, retry_policy=RetryPolicy(),
    )
    result = run_market_level(context)
    assert result.targets[0].output["operation"] == "index_chart"
    assert result.targets[0].output["entity_code"] == "0503"


def test_stock_investor_time_limit_is_detected_once_for_all_targets(monkeypatch):
    import app.batch.jobs.stock_details as job
    from app.batch.types import JobContext, RetryPolicy

    class FakeSession:
        def __enter__(self): return self
        def __exit__(self, *_): return None

    class FakeService:
        calls = 0

        def sync_stock_daily(self, *_args, **_kwargs):
            FakeService.calls += 1
            raise ValueError(
                "KIS stock-investor call failed: OPSQ2001 - TIME LIMIT 00:00 ~ 15:40"
            )

    monkeypatch.setattr(job, "SessionLocal", FakeSession)
    monkeypatch.setattr(job, "InvestorFlowService", FakeService)
    config = load_batch_config()
    context = JobContext(
        job_name="stock-investor-flow",
        config=config["jobs"]["stock-investor-flow"], batch_config=config,
        targets=["196170", "005930"], since=None, date="20260718",
        dry_run=False, retry_policy=RetryPolicy(max_attempts=3),
    )
    result = job.run_stock_details(context)
    assert result.success is True
    assert result.skipped == 2
    assert FakeService.calls == 1
    assert result.targets[0].output["error_code"] == "OPSQ2001"
    assert result.targets[1].output["first_observed_ticker"] == "196170"
