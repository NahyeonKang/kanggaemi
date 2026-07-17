# Batch orchestration (vertical slice 1-4)

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

For PostgreSQL, a session advisory lock prevents the same job across hosts. Non-PostgreSQL development uses a file lock under the OS temp directory, configurable with `BATCH_LOCK_DIR`.
