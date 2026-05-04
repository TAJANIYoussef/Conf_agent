# Conference Agent

> An autonomous AI agent that discovers, scores, and delivers academic conference deadlines directly to a researcher's inbox — tailored to a specific PhD thesis domain.

---

## Overview

**Conference Agent** is a ReAct-based agentic pipeline built for PhD researchers who need to stay current with relevant conference submission deadlines without manual monitoring. The agent autonomously searches multiple data sources, scores each conference for domain relevance using a large language model, and delivers a structured weekly HTML report via email.

The system is designed around hard cost and token constraints — each full pipeline run costs under **$0.05** in API usage — making it suitable for long-term weekly deployment on a personal machine.

---

## Motivation

Tracking academic conference deadlines across venues like NeurIPS, ICML, ICDM, KDD, ECML-PKDD, AAAI, and dozens of specialized workshops is time-consuming and error-prone. Existing tools (WikiCFP, ai-deadlines) require manual checking and do not filter for a researcher's specific domain.

This agent automates the full pipeline: discovery → relevance scoring → structured delivery, with zero manual effort after initial setup.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     Apache Airflow DAG                      │
│              (weekly schedule: every Monday 09:00)          │
└─────────────────────┬───────────────────────────────────────┘
                      │
          ┌───────────▼───────────┐
          │      run_agent()      │
          └───────────┬───────────┘
                      │
        ┌─────────────▼──────────────┐
        │   Stage 0: Aggregator Pull  │
        │  ai-deadlines (GitHub YAML) │
        │  dm-deadlines (GitHub YAML) │
        └─────────────┬──────────────┘
                      │
        ┌─────────────▼──────────────┐
        │  Stage 1: Search Loop       │  ← up to 5 iterations
        │  • DuckDuckGo (DDG search)  │
        │  • WikiCFP scraper          │
        │  • CFP page scraper         │
        └─────────────┬──────────────┘
                      │
        ┌─────────────▼──────────────┐
        │  Stage 2: Relevance Scoring │
        │  Claude Haiku (batch call)  │
        │  1 LLM call per iteration   │
        └─────────────┬──────────────┘
                      │
        ┌─────────────▼──────────────┐
        │  Stage 3: Email Delivery    │
        │  HTML table via Gmail SMTP  │
        └────────────────────────────┘
```

### Key Design Decisions

| Decision | Rationale |
|---|---|
| Claude Haiku only | Cost constraint: < $0.05/run absolute limit |
| Batch LLM scoring | 1 API call per iteration, not 1 per conference |
| Aggregator-first strategy | Community YAML feeds give structured data with no scraping needed for 50–100 conferences |
| ReAct loop with early exit | Stops when `MIN_CONFERENCES` found or 2 consecutive empty iterations |
| No cross-run deduplication | Researcher always receives the full current conference list each week |
| No async, no LangChain | Simpler, debuggable, no framework overhead |

---

## Data Sources

| Source | Type | Coverage |
|---|---|---|
| [ai-deadlines](https://github.com/abhshkdz/ai-deadlines) | Community YAML | ML, AI, DM, KR venues |
| [dm-deadlines](https://github.com/dm-deadlines/dm-deadlines.github.io) | Community YAML | Data mining focus |
| DuckDuckGo Search | Web search | Official CFP pages |
| WikiCFP | Structured scrape | Broad CFP database |
| Official CFP pages | HTML scrape | Ground-truth deadlines |

---

## Relevance Scoring

Each conference candidate is scored 0–10 by Claude Haiku against the researcher's thesis keywords and abstract:

| Score | Category | Examples |
|---|---|---|
| 10 | Perfect match | Imbalanced learning, SMOTE, synthetic tabular data |
| 7–9 | Strong match | NeurIPS, ICML, ICDM, ECML-PKDD, AAAI, IJCAI, KDD |
| 4–6 | Adjacent | Statistics, databases, feature engineering |
| 0–3 | Irrelevant | NLP-only, CV-only, non-research events |

Only conferences scoring ≥ 4 are included in the email report.

---

## Project Structure

```
conference_agent/
├── agent/
│   ├── agent.py           # ReAct loop — main orchestration logic
│   ├── config.py          # All thresholds, prompts, and constants
│   ├── main.py            # Entry point — thesis keywords & abstract
│   └── models.py          # Pydantic schemas (Conference, AgentState, AgentRunResult)
├── tools/
│   ├── aggregators.py     # YAML feed fetcher (ai-deadlines, dm-deadlines)
│   ├── relevance.py       # Batch LLM scoring via Claude Haiku
│   ├── search.py          # DuckDuckGo search with LRU cache
│   ├── webpage_scraper.py # Multi-strategy CFP page date extractor
│   ├── wikicfp.py         # WikiCFP structured scraper
│   └── email_tool.py      # HTML email builder and Gmail SMTP sender
├── memory/
│   └── store.py           # Run history and cost tracking (JSON flat file)
├── airflow/
│   └── dags/
│       └── conference_agent_dag.py  # Airflow DAG definition
├── tests/                 # Pytest test suite
├── logs/                  # Per-run timestamped logs
├── memory_store.json      # Persistent run history
├── airflow.service        # systemd service unit
├── requirements.txt
└── .env                   # API keys (not committed)
```

---

## Installation

### 1. Clone and create environment

```bash
git clone https://github.com/TAJANIYoussef/conf_agent.git
cd conference_agent
conda create -n cal_ag python=3.12
conda activate cal_ag
pip install -r requirements.txt
```

### 2. Install Airflow (Python 3.12 requires Airflow 2.10+)

```bash
pip install "apache-airflow==2.10.4" \
  --constraint "https://raw.githubusercontent.com/apache/airflow/constraints-2.10.4/constraints-3.12.txt"
```

### 3. Configure environment variables

Create a `.env` file in the project root:

```env
ANTHROPIC_API_KEY=sk-ant-...
EMAIL_FROM=your-gmail@gmail.com
EMAIL_TO=your-inbox@gmail.com
EMAIL_APP_PASSWORD=xxxx xxxx xxxx xxxx
```

> **Gmail App Password**: Google Account → Security → 2-Step Verification → App Passwords → Generate

### 4. Customize thesis context

Edit `agent/main.py` to set your own keywords and abstract:

```python
THESIS_KEYWORDS = [
    "imbalanced learning",
    "class imbalance",
    "oversampling",
    "SMOTE",
    # add your own ...
]

THESIS_ABSTRACT = """
Your thesis abstract here...
"""
```

---

## Running

**Dry run — finds conferences but skips email:**
```bash
python -m agent.main --dry-run
```

**Full live run:**
```bash
python -m agent.main
```

**Trigger manually via Airflow:**
```bash
airflow dags trigger conference_weekly
```

---

## Airflow Setup (Weekly Automation)

Initialize the Airflow database and point it at the project DAG:

```bash
export AIRFLOW_HOME=~/airflow
echo 'export AIRFLOW_HOME=~/airflow' >> ~/.bashrc
airflow db migrate
sed -i 's|dags_folder = .*|dags_folder = /path/to/conference_agent/airflow/dags|' ~/airflow/airflow.cfg
```

Install as a systemd service so Airflow starts automatically on boot:

```bash
sudo cp airflow.service /etc/systemd/system/airflow.service
sudo systemctl daemon-reload
sudo systemctl enable airflow
sudo systemctl start airflow
```

Access the Airflow UI at **http://localhost:8080**, enable the `conference_weekly` DAG, and it will execute every Monday at 09:00.

---

## Cost Profile

| Component | Cost per run |
|---|---|
| Query generation (1 Haiku call) | ~$0.001 |
| Relevance scoring (Haiku, all iterations) | ~$0.003–$0.004 |
| **Total** | **< $0.05** |

Token budget: 15,000 input tokens max per run. All candidates within each iteration are batched into a single LLM call to stay within budget.

---

## Email Output

Each weekly run delivers an HTML email containing a full conference table with:

- Conference acronym and full name (hyperlinked to CFP page)
- Abstract submission deadline
- Full paper deadline
- Camera-ready deadline
- Conference date and venue
- Relevance score and one-sentence justification

Conferences are sorted by relevance score in descending order.

---

## Environment

| Component | Detail |
|---|---|
| OS | Ubuntu 24.04 |
| Python | 3.12 |
| LLM | Claude Haiku (`claude-haiku-4-5-20251001`) |
| Orchestration | Apache Airflow 2.10 standalone, SQLite backend |
| Hardware | Intel i7 10th gen, 24 GB RAM (CPU-only) |

---

## PhD Context

This agent was built to support research on **class imbalance in mixed-type tabular data** at the LIAS Laboratory, Faculty of Ben M'Sik, Hassan II University, Casablanca, Morocco.

Target venues include NeurIPS, ICML, ICDM, ECML-PKDD, KDD, AAAI, IJCAI, PAKDD, CIKM, AISTATS, SDM, and workshops on imbalanced learning, tabular data, and synthetic data generation.

---

## License

MIT
