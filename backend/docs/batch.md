# Batch orchestration

The application owns no schedule. Cron or Airflow invokes one idempotent CLI job and uses its exit code.

## Setup and commands

Create the market-cap prerequisite and new point-in-time table once. The command is idempotent and can be rerun safely:

```bash
python -m scripts.create_universe_membership_table
```

This ensures both `market_cap_ranking` and `universe_membership`. Batch jobs intentionally do not create production tables automatically.

Inspect work without external API calls or writes:

```bash
python -m app.batch.run universe-refresh --dry-run
python -m app.batch.run stock-prices --targets 005930 000660 --since 20260101 --dry-run
```

Dry runs skip the execution lock because they perform no writes. Without explicit stock targets, the stock dry run still reads the database to resolve the latest complete membership.

Run the weekly producer and daily consumer:

```bash
python -m app.batch.run universe-refresh
python -m app.batch.run stock-prices
```

Explicit targets override configured markets or latest membership:

```bash
python -m app.batch.run universe-refresh --targets kospi
python -m app.batch.run stock-prices --targets 005930,000660 --since 20260101 --date 20260718
```

Exit codes are `0` for success, `1` for a completed/uncaught job failure, `2` for invalid configuration or arguments, and `3` when the same job is already running. A target failure does not stop later targets, but makes the final exit code non-zero.

`jobs.yaml` declares schedules, dependencies, universe sizes, service parameters, and retry policy. Change `markets.*.top_n` to expand the universe without code changes.

The stock job ignores a newer partial membership date and selects the newest date that satisfies every configured market count. This prevents a failed half of `universe-refresh` from silently shrinking the downstream universe.

## Scheduling

`deploy/crontab.example` invokes `deploy/run_daily_batch.sh` at 05:00 Asia/Seoul. On Sundays the wrapper runs `universe-refresh` first and only then runs `stock-prices`; on other days it consumes the latest membership.

`deploy/airflow_kanggaemi_batch.py` expresses the same branch and dependency while still calling the same CLI. The DAG has `max_active_runs=1`; application-level locks remain the final overlap guard.

KIS documents access-token reissuance as limited to once per minute. The cron/Airflow chain therefore waits 65 seconds between all KIS-backed CLI processes. Each KIS job also uses a deterministic 65-second first retry interval so an immediately repeated manual CLI run can recover without changing the collection services.

Jobs declaring `uses_kis: true` also reserve a host-local token slot before their first API call. The timestamp and cross-process lock live under the OS temp batch-lock directory (override with `BATCH_KIS_TOKEN_STATE_DIR`). A CLI started within 65 seconds of the previous KIS batch waits only the remaining interval and logs `kis_token_throttle_wait`, avoiding an initial `/oauth2/tokenP` 403. `futures-sync` shares one auth client between its overseas and domestic chart scrapers so it issues only one token in that process.

For PostgreSQL, a session advisory lock prevents the same job across hosts. Non-PostgreSQL development uses a file lock under the OS temp directory, configurable with `BATCH_LOCK_DIR`.

## Futures master and active-contract cache (step 5)

Apply the idempotent schema migration before the first resolver run:

```bash
python -m scripts.create_active_contract_table
```

It creates both master tables when absent, adds the four `ffcode.mst` tail-flag columns to an existing `overseas_future_master`, and creates `active_contract`.

Inspect and run the weekly master loaders:

```bash
python -m app.batch.run futures-master-refresh --dry-run
python -m app.batch.run futures-master-refresh
```

The job invokes the existing loader modules with `--download`. Overseas and domestic loaders are isolated targets, so one failure does not prevent the other attempt.

Resolve the five overseas products and domestic KOSPI200 future:

```bash
python -m app.batch.run active-contract-refresh --dry-run
python -m app.batch.run active-contract-refresh
```

Overseas resolution prefers `most_active_flag=1` and falls back to `nearest_flag=1`; spread series codes containing `-` are excluded. Domestic resolution treats `product_type=1` as a future, parses `YYYYMM` from names such as `F 202609`, calculates the second Thursday, takes the nearest three unexpired contracts, and compares volume on their latest common trading date. The daily cache is append-only across dates and idempotently updated within the same date. A same-day row is recomputed only when its master has since changed.

## Futures and fixed/stock-domain jobs (steps 6-7)

The futures collector consumes only the exact-date `active_contract` cache. It never resolves or stores a hard-coded expiry code itself:

```bash
python -m app.batch.run active-contract-refresh --date 20260718
python -m app.batch.run futures-sync --date 20260718
python -m app.batch.run futures-sync --targets overseas:WTI domestic:KOSPI200 --since 20260101 --date 20260718 --dry-run
```

`--since` is passed to the domestic chart API. The overseas futures API exposes a close-date plus page count rather than a start date, so an overseas target uses `--date` as `close_date` and the configured `overseas_max_pages` as its backfill bound.

Known non-retryable KIS account-entitlement errors are declared in `skip_entitlement_error_codes`. The `SUB거래소 신청 계좌가 아닙니다` marker also classifies newly encountered SUB-exchange codes without a slow retry cycle. For example, NYMEX `EGW00551` and COMEX `EGW00553` are logged once as `target_skipped` with the product, active contract, exchange and original message; they do not prevent the remaining futures targets from running. The final `job_finished` event reports separate `succeeded`, `skipped` and `failed` counts.

Daily fixed-target jobs are:

```bash
python -m app.batch.run market-indices       # KOSPI/KOSDAQ/KOSPI200/VKOSPI
python -m app.batch.run market-investor-flow # KOSPI/KOSDAQ
python -m app.batch.run market-program-trade # KOSPI/KOSDAQ
python -m app.batch.run market-funds
python -m app.batch.run macro-indicators
python -m app.batch.run yield-rates
python -m app.batch.run exchange-rates
```

VKOSPI is declared as `entity_code=0503` under the `index_chart` operation; it is never sent through futures resolution. USD/KRW daily defaults to a 14-calendar-day overlap and accepts `--since` for a longer backfill. Market program and index jobs also pass `--since` directly. Other services retain their existing API's date/window semantics. Append-only intraday endpoints (`yield.sync_snapshots` and `exchange.sync_usdkrw_summary`) are deliberately excluded because rerunning them creates a new observation rather than an idempotent upsert.

Latest complete universe membership drives the remaining stock jobs:

```bash
python -m app.batch.run stock-investor-flow
python -m app.batch.run stock-program-trade
python -m app.batch.run stock-financials       # annual and quarterly, weekly schedule
```

The stock investor endpoint rejects same-day requests before 15:40 with `OPSQ2001`. When `--date` is omitted, the 05:00 batch therefore resolves the latest Korean business date whose 15:40 close is complete (including weekends and Korean holidays) and passes that date to the existing service. If KIS still returns the endpoint-wide time limit, only the first ticker probes the API; every remaining ticker is immediately reported as `target_skipped` without 65/130-second retries.

Every target is isolated and retried; all targets are attempted and any final target failure makes the CLI exit non-zero. The provided cron wrapper and Airflow DAG preserve master -> resolver -> futures sync and universe -> stock-detail ordering. Their 65-second gaps are intentional because each existing KIS service owns its own authentication client.
