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
    return "universe_refresh" if logical_date.in_timezone("Asia/Seoul").isoweekday() == 7 else "universe_not_due"


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
    universe = BashOperator(
        task_id="universe_refresh",
        bash_command=f'cd "{BACKEND}" && "{PYTHON}" -m app.batch.run universe-refresh',
    )
    not_due = EmptyOperator(task_id="universe_not_due")
    membership_ready = EmptyOperator(
        task_id="membership_ready",
        trigger_rule="none_failed_min_one_success",
    )
    stock_prices = BashOperator(
        task_id="stock_prices",
        bash_command=f'cd "{BACKEND}" && "{PYTHON}" -m app.batch.run stock-prices',
    )

    branch >> [universe, not_due] >> membership_ready >> stock_prices

