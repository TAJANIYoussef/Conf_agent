Run the conference agent in dry-run mode (no Google Calendar writes).

Steps:
1. Execute: `python agent/main.py --dry-run`
2. Wait for completion and capture output
3. Show a clean summary:
   - Number of conferences found
   - Top 5 by relevance score with acronym, year, deadline date, score
   - Total iterations used
   - Estimated API cost from logs
   - Total input/output tokens used
4. Highlight any errors or warnings from the log output
