Show full agent status report.

Steps:
1. Read memory_store.json and display:
   - Total conferences tracked: N
   - Date of last run
   - All-time runs: N runs, total cost $X
   - List of tracked acronyms (sorted, formatted as a table)

2. Check environment:
   - Confirm ANTHROPIC_API_KEY present in .env (do NOT show the value)
   - Confirm BRAVE_API_KEY present in .env (do NOT show the value)
   - Confirm gcal_credentials.json exists
   - Confirm gcal_token.json exists (OAuth done) or warn if missing

3. Check Airflow:
   - Run `airflow dags list` and show result
   - Run `airflow dags state conference_weekly $(date +%Y-%m-%d)` for latest run state

4. Show most recent log file content (last 30 lines)
