#!/bin/bash
# Runs on every boot. Triggers the conference agent if it hasn't run in the last 7 days.
# This gives you a weekly briefing regardless of which day you boot.

AIRFLOW="/home/tajani-youssef/anaconda3/envs/conference_agent/bin/airflow"
AIRFLOW_HOME="/home/tajani-youssef/airflow"
LOG="$AIRFLOW_HOME/trigger.log"
STAMP="$AIRFLOW_HOME/last_agent_run"
COOLDOWN_DAYS=6

export AIRFLOW_HOME

echo "[$(date '+%Y-%m-%d %H:%M:%S')] Boot trigger started" >> "$LOG"

# Check if agent already ran within the last 6 days
if [ -f "$STAMP" ]; then
    last=$(cat "$STAMP")
    now=$(date +%s)
    diff=$(( (now - last) / 86400 ))
    if [ "$diff" -lt "$COOLDOWN_DAYS" ]; then
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] Ran ${diff} day(s) ago — skipping (next run in $((COOLDOWN_DAYS - diff)) day(s))." >> "$LOG"
        exit 0
    fi
fi

echo "[$(date '+%Y-%m-%d %H:%M:%S')] Weekly briefing due — waiting for Airflow..." >> "$LOG"

# Wait up to 2 minutes for Airflow to be ready
for i in $(seq 1 24); do
    if "$AIRFLOW" dags list > /dev/null 2>&1; then
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] Airflow is ready." >> "$LOG"
        break
    fi
    sleep 5
done

# Skip if a run is already active
RUNNING=$("$AIRFLOW" dags list-runs -d conference_weekly --state running --state queued 2>/dev/null | grep -c "conference_weekly" || true)
if [ "$RUNNING" -gt "0" ]; then
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] DAG already running/queued — skipping." >> "$LOG"
    exit 0
fi

echo "[$(date '+%Y-%m-%d %H:%M:%S')] Triggering conference_weekly..." >> "$LOG"
"$AIRFLOW" dags trigger conference_weekly >> "$LOG" 2>&1
date +%s > "$STAMP"
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Done. Next run in ~7 days." >> "$LOG"
