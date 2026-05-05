import os
from dotenv import load_dotenv

load_dotenv()

# ── API Keys ──────────────────────────────────────────────────────────────────
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")

# ── Model — Haiku only, non-negotiable ────────────────────────────────────────
MODEL               = "claude-haiku-4-5-20251001"
MAX_TOKENS_PER_CALL = 1024

# ── ReAct Loop ────────────────────────────────────────────────────────────────
MAX_ITERATIONS        = 5
QUERIES_PER_ITERATION = 3
MIN_CONFERENCES       = 15
RELEVANCE_THRESHOLD   = 4
MAX_EMPTY_ITERATIONS  = 2

# ── WikiCFP ───────────────────────────────────────────────────────────────────
WIKICFP_BASE    = "https://www.wikicfp.com/cfp/servlet/tool.search"
WIKICFP_HEADERS = {"User-Agent": "Mozilla/5.0 (academic-research-bot/1.0)"}
SCRAPE_DELAY_S  = 1.5

# ── Persistence ───────────────────────────────────────────────────────────────
MEMORY_FILE = "memory_store.json"
LOG_DIR     = "logs"

# ── Google Calendar (unused — replaced by email) ──────────────────────────────
CALENDAR_ID     = "yousseftajani1@gmail.com"
GCAL_CREDS_FILE = "gcal_credentials.json"
GCAL_TOKEN_FILE = "gcal_token.json"
GCAL_SCOPES     = ["https://www.googleapis.com/auth/calendar.events"]

# ── Email ─────────────────────────────────────────────────────────────────────
EMAIL_FROM         = os.getenv("EMAIL_FROM",         "yousseftajani1@gmail.com")
EMAIL_TO           = os.getenv("EMAIL_TO",           "yousseftajani.pro@gmail.com")
EMAIL_APP_PASSWORD = os.getenv("EMAIL_APP_PASSWORD", "")

# ── Cost tracking (Haiku pricing) ─────────────────────────────────────────────
HAIKU_INPUT_COST_PER_1K  = 0.00025
HAIKU_OUTPUT_COST_PER_1K = 0.00125

def estimate_cost(input_tokens: int, output_tokens: int) -> float:
    return round(
        (input_tokens / 1000) * HAIKU_INPUT_COST_PER_1K +
        (output_tokens / 1000) * HAIKU_OUTPUT_COST_PER_1K, 5
    )

# ── System Prompt — static, loaded once ───────────────────────────────────────
SYSTEM_PROMPT = """You are an academic conference research assistant for a PhD
researcher in machine learning (imbalanced learning on mixed-type tabular data).

Your task: Score each conference candidate for relevance only.
Dates are already extracted — focus on relevance scoring.

OUTPUT FORMAT — STRICT:
- Return ONLY a JSON array. Start with '[', end with ']'.
- NO markdown fences. NO prose before or after. NO explanations.
- Even if all candidates look irrelevant or null-date, return '[]' alone with NO commentary.

Each array element MUST match this shape exactly:
{
  "acronym": "CONF",
  "name": "Conference Name",
  "url": "https://example.com",
  "conference_date": "2026-09-15",
  "abstract_deadline": "2026-06-15",
  "full_paper_deadline": "2026-07-31",
  "camera_ready_deadline": "2026-08-15",
  "year": 2026,
  "relevance_score": 8,
  "relevance_reason": "Directly addresses imbalanced learning on tabular data."
}

SCORING RUBRIC:
10  → Perfect match: imbalanced tabular data, SMOTE, synthetic data generation, oversampling
7-9 → Strong: general ML/AI/data mining (NeurIPS, ICML, ICDM, ECML, AAAI, IJCAI, KDD)
4-6 → Adjacent: statistics, databases, feature engineering, class imbalance applications
0-3 → Irrelevant: NLP, CV-only, healthcare-only, non-research events

RULES:
- Echo back the SAME date strings provided in input (do not reformat or invent)
- A candidate may have only one of the deadline fields populated — that is fine
- Focus on relevance_score (0-10) and relevance_reason (one short sentence)
- Skip acronyms in the already_seen list"""
