import json
import logging
import re
from datetime import date
from anthropic import Anthropic
from agent.config import (MODEL, MAX_TOKENS_PER_CALL, ANTHROPIC_API_KEY,
                          RELEVANCE_THRESHOLD, SYSTEM_PROMPT, estimate_cost)
from agent.models import Conference

logger = logging.getLogger(__name__)
client = Anthropic(api_key=ANTHROPIC_API_KEY)

_total_input_tokens  = 0
_total_output_tokens = 0

def get_total_tokens() -> tuple[int, int]:
    return _total_input_tokens, _total_output_tokens


def _extract_json_array(text: str):
    """
    Pull the first balanced JSON array out of a string and parse it.
    Tolerates leading/trailing prose and code fences. Returns None on failure.
    """
    if not text:
        return None
    start = text.find("[")
    if start == -1:
        return None
    depth = 0
    in_str = False
    escape = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_str:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "[":
            depth += 1
        elif ch == "]":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(text[start:i + 1])
                except json.JSONDecodeError:
                    return None
    return None

def batch_score_conferences(
    raw_candidates: list[dict],
    thesis_keywords: list[str],
    thesis_summary: str,
    seen_acronyms: set[str],
) -> list[Conference]:
    """
    ONE single Haiku API call scores all candidates.
    Uses pre-extracted dates from webpage scraper (no need to ask LLM for dates).
    Pre-filters seen_acronyms to avoid wasting tokens.
    """
    global _total_input_tokens, _total_output_tokens

    # Remove already-seen conferences before sending to LLM
    def _candidate_key(c: dict) -> str:
        acronym = c.get("acronym", "").upper().strip()[:12]
        raw = c.get("when", "") + " " + c.get("deadline", "")
        year = next((w for w in raw.split() if w.isdigit() and len(w) == 4), "2026")
        return f"{acronym}{year}"

    candidates = [
        c for c in raw_candidates
        if _candidate_key(c) not in seen_acronyms
    ]
    if not candidates:
        return []

    # Slim payload — only fields relevant to scoring (dates already extracted)
    slim = [
        {
            "acronym":  c.get("acronym", "")[:15],
            "name":     c.get("name", "")[:150],
            "url":      c.get("url", ""),
            "conference_date": c.get("conference_date"),
            "abstract_deadline": c.get("abstract_deadline"),
            "full_paper_deadline": c.get("full_paper_deadline"),
            "camera_ready_deadline": c.get("camera_ready_deadline"),
        }
        for c in candidates
    ]

    prompt = (
        f"Thesis keywords: {', '.join(thesis_keywords)}\n"
        f"Summary: {thesis_summary}\n"
        f"Already seen (do not include): {', '.join(list(seen_acronyms)[:25])}\n\n"
        f"Score these {len(slim)} candidates for relevance ONLY (dates already extracted):\n"
        f"{json.dumps(slim, default=str)}\n\n"
        "Return ONLY the JSON array with relevance_score (0-10) and relevance_reason. No markdown fences."
    )

    try:
        resp = client.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS_PER_CALL,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
        )
    except Exception as e:
        logger.error(f"Haiku call failed: {e}")
        return []

    _total_input_tokens  += resp.usage.input_tokens
    _total_output_tokens += resp.usage.output_tokens
    cost = estimate_cost(resp.usage.input_tokens, resp.usage.output_tokens)
    logger.info(f"  [tokens] in={resp.usage.input_tokens} "
                f"out={resp.usage.output_tokens} cost≈${cost}")

    raw = resp.content[0].text.strip()
    if raw.startswith("```"):
        raw = "\n".join(
            l for l in raw.splitlines()
            if not l.strip().startswith("```")
        ).strip()

    # Robust extraction: Haiku occasionally appends prose after the JSON array
    # (e.g. "[]\n\nAll N candidates have null values..."). Pull the first
    # bracket-balanced array out of the text and parse only that.
    data = _extract_json_array(raw)
    if data is None:
        logger.error(f"JSON parse failed — raw[:300]: {raw[:300]}")
        return []

    if not isinstance(data, list):
        logger.error(f"Expected JSON array, got {type(data)}")
        return []

    scored = []
    today = date.today()
    for idx, item in enumerate(data):
        try:
            if not isinstance(item, dict):
                continue
            conf = Conference(**item)
            logger.debug(f"{idx}. {conf.acronym} score={conf.relevance_score} dates={conf.abstract_deadline or conf.full_paper_deadline or conf.camera_ready_deadline or 'NONE'}")
            if not (conf.abstract_deadline or conf.full_paper_deadline or conf.camera_ready_deadline):
                logger.debug(f"  → Skipping {conf.acronym} — no deadline dates available")
                continue
            if (conf.full_paper_deadline and conf.full_paper_deadline < today) or \
               (conf.camera_ready_deadline and conf.camera_ready_deadline < today):
                logger.debug(f"  → Skipping {conf.acronym} — deadline(s) in the past")
                continue
            logger.info(f"  ✓ ACCEPTED: {conf.acronym} {conf.year} (score {conf.relevance_score})")
            scored.append(conf)
        except Exception as e:
            logger.debug(f"Item {idx} validation failed: {e}")
            continue
    return scored
