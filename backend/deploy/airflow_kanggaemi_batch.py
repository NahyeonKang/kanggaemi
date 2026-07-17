"""Airflow equivalent of the 05:00 Asia/Seoul cron orchestration.

Copy into the Airflow DAG folder and set KANGGAEMI_BACKEND/KANGGAEMI_PYTHON
in the scheduler environment. Airflow only schedules the same application CLI.
"""

from __future__ import annotations

import os
from datetime import datetime

import pendulum
from airflow import DAG
from airflow.operators.bash import BashOperator
from airflow.operators.empty import EmptyOperator
from airflow.operators.python import BranchPythonOperator


BACKEND = os.environ.get("KANGGAEMI_BACKEND", "/opt/kanggaemi/backend")
PYTHON = os.environ.get("KANGGAEMI_PYTHON", "/opt/kanggaemi/venv/bin/python")


def choose_universe_task(*, logical_date: datetime, **_: object) -> str:
    return "futures_master_refresh" if logical_date.in_timezone("Asia/Seoul").isoweekday() == 7 else "weekly_not_due"


with DAG(
    dag_id="kanggaemi_daily_batch",
    schedule="0 5 * * *",
    start_date=pendulum.datetime(2026, 1, 1, tz="Asia/Seoul"),
    catchup=False,
    max_active_runs=1,
    default_args={"retries": 0},  # target retries are inside the CLI; whole-job retries belong here when desired
    tags=["kanggaemi", "batch"],
) as dag:
    branch = BranchPythonOperator(
        task_id="is_universe_refresh_day",
        python_callable=choose_universe_task,
    )
    futures_master = BashOperator(
        task_id="futures_master_refresh",
        bash_command=f'cd "{BACKEND}" && "{PYTHON}" -m app.batch.run futures-master-refresh',
    )
    universe = BashOperator(
        task_id="universe_refresh",
        bash_command=f'cd "{BACKEND}" && "{PYTHON}" -m app.batch.run universe-refresh',
    )
    not_due = EmptyOperator(task_id="weekly_not_due")
    membership_ready = EmptyOperator(
        task_id="membership_ready",
        trigger_rule="none_failed_min_one_success",
    )
    def cli(task_id: str, job: str) -> BashOperator:
        return BashOperator(
            task_id=task_id,
            bash_command=f'cd "{BACKEND}" && "{PYTHON}" -m app.batch.run {job}',
        )

    def cooldown(task_id: str) -> BashOperator:
        return BashOperator(task_id=task_id, bash_command="sleep 65")

    universe_cooldown = cooldown("universe_token_cooldown")
    stock_financials = cli("stock_financials", "stock-financials")
    financials_cooldown = cooldown("financials_token_cooldown")
    active_contracts = BashOperator(
        task_id="active_contract_refresh",
        bash_command=f'cd "{BACKEND}" && "{PYTHON}" -m app.batch.run active-contract-refresh',
    )
    resolver_cooldown = cooldown("resolver_token_cooldown")
    futures_sync = cli("futures_sync", "futures-sync")
    futures_cooldown = cooldown("futures_token_cooldown")
    market_indices = cli("market_indices", "market-indices")
    indices_cooldown = cooldown("indices_token_cooldown")
    market_investor = cli("market_investor_flow", "market-investor-flow")
    investor_cooldown = cooldown("market_investor_token_cooldown")
    market_program = cli("market_program_trade", "market-program-trade")
    program_cooldown = cooldown("market_program_token_cooldown")
    market_funds = cli("market_funds", "market-funds")
    funds_cooldown = cooldown("market_funds_token_cooldown")
    stock_prices = cli("stock_prices", "stock-prices")
    prices_cooldown = cooldown("stock_prices_token_cooldown")
    stock_investor = cli("stock_investor_flow", "stock-investor-flow")
    stock_investor_cooldown = cooldown("stock_investor_token_cooldown")
    stock_program = cli("stock_program_trade", "stock-program-trade")
    macro = cli("macro_indicators", "macro-indicators")
    yields = cli("yield_rates", "yield-rates")
    exchange = cli("exchange_rates", "exchange-rates")

    branch >> futures_master >> universe >> universe_cooldown >> stock_financials >> financials_cooldown
    branch >> not_due
    [financials_cooldown, not_due] >> membership_ready
    membership_ready >> active_contracts >> resolver_cooldown >> futures_sync >> futures_cooldown
    futures_cooldown >> market_indices >> indices_cooldown >> market_investor >> investor_cooldown
    investor_cooldown >> market_program >> program_cooldown >> market_funds >> funds_cooldown
    funds_cooldown >> stock_prices >> prices_cooldown
    prices_cooldown >> stock_investor >> stock_investor_cooldown >> stock_program
    stock_program >> macro >> yields >> exchange
