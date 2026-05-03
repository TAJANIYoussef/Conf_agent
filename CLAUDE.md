# Conference Agent — Claude Code Memory

## What this project is
A Python agent that finds academic conferences relevant to a PhD thesis
(imbalanced learning, tabular data, AutoSMOTE-NC) and writes their deadlines
to Google Calendar. Scheduled weekly via Apache Airflow standalone mode.

## Architecture decisions (do not change without asking)
- Model: claude-haiku-4-5-20251001 ONLY — cost constraint is absolute
- Loop: ReAct, max 5 iterations, stops early at 2 consecutive empty results
- Memory: JSON flat file (memory_store.json) — no vector DB needed
- Orchestration: Apache Airflow standalone on local Ubuntu machine
- No async, no LangChain, no streaming

## Active constraints
- Max $0.05 per agent run (Anthropic API cost)
- Max 15,000 input tokens total across all LLM calls per run
- Batch ALL relevance scoring into ONE Haiku call per iteration
- Never send raw HTML to the LLM — always extract text with BeautifulSoup first
- lru_cache on ddg_search — same query never hits the API twice in one run

## File ownership map
- agent/config.py      → system prompt + all thresholds (edit here first)
- agent/models.py      → Pydantic schemas (single source of truth for data shape)
- agent/agent.py       → ReAct loop logic
- memory/store.py      → cross-run state persistence (memory_store.json)
- airflow/dags/        → scheduling and orchestration

## Common tasks
- Test without calendar: `python agent/main.py --dry-run`
- Check token cost:     logs/ directory, each run has a timestamped log
- Reset seen confs:     /reset-memory (slash command) or delete memory_store.json
- Airflow status:       `airflow dags list` / `airflow dags trigger conference_weekly`
- Run tests:            `pytest tests/ -v`

## Environment
- OS: Ubuntu 24.04, Python 3.11+
- Hardware: Intel i7 10th gen, 24GB RAM, NVIDIA MX330
- MX330 is NOT used — this project is CPU + API only
- Airflow: standalone mode, SQLite backend (local development)
- Anaconda environment recommended: conda activate conference_agent

## PhD context (used for conference relevance scoring)
- Researcher: Youssef, PhD candidate, Hassan II University, Casablanca, Morocco
- Lab: LIAS laboratory, Faculty of Ben M'Sik
- Thesis: Novel AI approaches for class imbalance in mixed-type tabular data
- Key paper: AutoSMOTE-NC — decision-based oversampling with Gumbel-Softmax + VDM
- Submitted to: Array (Elsevier)
- Target conferences: NeurIPS, ICML, ICDM, ECML, PAKDD, AAAI, IJCAI,
  workshops on imbalanced learning, tabular data, synthetic data generation
