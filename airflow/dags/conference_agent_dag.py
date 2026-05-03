"""
DAG: conference_weekly
Schedule: every Monday at 09:00
catchup=False — only runs going forward, no backfill
max_active_runs=1 — never two instances at once
"""
import os
import sys
import logging
from datetime import datetime, timedelta
from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.operators.bash import BashOperator

PROJECT_ROOT = os.path.expanduser("~/Desktop/cal_ag/conference_agent")

default_args = {
    "owner":            "youssef",
    "retries":          1,
    "retry_delay":      timedelta(minutes=5),
    "email_on_failure": False,
    "email_on_retry":   False,
}


def run_conference_agent(**context):
    os.chdir(PROJECT_ROOT)
    if PROJECT_ROOT not in sys.path:
        sys.path.insert(0, PROJECT_ROOT)

    from dotenv import load_dotenv
    load_dotenv(os.path.join(PROJECT_ROOT, ".env"))

    from agent.agent import run_agent
    from agent.main import THESIS_KEYWORDS, THESIS_ABSTRACT

    result = run_agent(THESIS_KEYWORDS, THESIS_ABSTRACT, dry_run=False)

    logging.info(
        f"Run complete: {result.conferences_added} conferences, "
        f"${result.estimated_cost_usd:.4f} cost, "
        f"{result.iterations_used} iterations"
    )
    return result.conferences_added


with DAG(
    dag_id="conference_weekly",
    description="PhD conference finder — weekly email report",
    default_args=default_args,
    schedule_interval="0 9 * * 1",   # every Monday at 09:00
    start_date=datetime(2026, 5, 4),
    catchup=False,
    max_active_runs=1,
    tags=["phd", "research"],
) as dag:

    t1_check = BashOperator(
        task_id="check_env",
        bash_command=(
            f"cd {PROJECT_ROOT} && "
            "python -c \""
            "from dotenv import load_dotenv; load_dotenv(); import os; "
            "assert os.getenv('ANTHROPIC_API_KEY'), 'ANTHROPIC_API_KEY missing'; "
            "assert os.getenv('EMAIL_APP_PASSWORD'), 'EMAIL_APP_PASSWORD missing'; "
            "print('ENV OK')\""
        ),
    )

    t2_run = PythonOperator(
        task_id="run_agent",
        python_callable=run_conference_agent,
        provide_context=True,
    )

    t1_check >> t2_run
