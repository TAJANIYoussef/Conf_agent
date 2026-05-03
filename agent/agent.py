import json
import logging
from anthropic import Anthropic
from agent.models import AgentState, Conference, AgentRunResult
from agent.config import (MODEL, ANTHROPIC_API_KEY, MAX_ITERATIONS,
                          QUERIES_PER_ITERATION, MIN_CONFERENCES,
                          MAX_EMPTY_ITERATIONS, estimate_cost,
                          EMAIL_FROM, EMAIL_TO, EMAIL_APP_PASSWORD)
from tools.search import ddg_search
from tools.wikicfp import search_wikicfp
from tools.relevance import batch_score_conferences, get_total_tokens
from tools.email_tool import send_conference_email
from tools.webpage_scraper import extract_from_search_result, is_scrapable_url
from tools.aggregators import fetch_aggregator_candidates
from memory.store import get_seen_acronyms, mark_added, record_run

logger = logging.getLogger(__name__)
client = Anthropic(api_key=ANTHROPIC_API_KEY)

# Words to strip when building short WikiCFP queries
_STOPWORDS = {"cfp","call","for","papers","deadline","2026","2027",
              "conference","workshop","international","annual"}

# Hand-curated, conference-targeted search queries. These reliably surface
# the official CFP page in the top few DDG results — far higher signal than
# Haiku-invented queries like "CFP imbalanced learning 2026" which mostly
# return blog posts.
_CURATED_QUERIES = [
    "NeurIPS 2026 call for papers important dates",
    "ICML 2026 call for papers important dates",
    "ICLR 2026 call for papers important dates",
    "ICDM 2026 call for papers submission deadline",
    "KDD 2026 call for papers research track",
    "ECML PKDD 2026 call for papers",
    "AAAI 2026 call for papers",
    "IJCAI 2026 call for papers",
    "PAKDD 2026 call for papers",
    "CIKM 2026 call for papers",
    "SDM 2026 call for papers SIAM data mining",
    "AISTATS 2026 call for papers",
    "AutoML 2026 call for papers",
    "DSAA 2026 call for papers data science",
    "BigData 2026 IEEE call for papers",
]


def _generate_queries(keywords: list[str], summary: str) -> list[str]:
    """
    ONE upfront Haiku call generates topic-specific search queries; we then
    interleave them with the curated list of CFP-targeted queries.
    """
    n = MAX_ITERATIONS * QUERIES_PER_ITERATION
    prompt = (
        f"Generate {n} search queries to find academic conference CFP pages "
        f"relevant to this PhD thesis. Target official conference websites, "
        f"not blog posts or tutorials.\n\n"
        f"Keywords: {', '.join(keywords)}\n"
        f"Summary: {summary}\n\n"
        f"Return ONLY a JSON array of {n} strings. No markdown. No prose.\n"
        f"Rules:\n"
        f"- Each query MUST contain 'call for papers' or 'CFP' AND '2026'\n"
        f"- Prefer specific conference acronyms over generic topics\n"
        f"- Each query must be different — no duplicates\n"
        f'Example format: ["NeurIPS 2026 call for papers imbalanced learning", '
        f'"ICDM 2026 CFP tabular data workshop"]'
    )
    try:
        resp = client.messages.create(
            model=MODEL,
            max_tokens=512,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = resp.content[0].text.strip()
        if raw.startswith("```"):
            raw = "\n".join(
                l for l in raw.splitlines()
                if not l.strip().startswith("```")
            ).strip()
        # Find first JSON array (defensive against trailing prose)
        import re as _re
        m = _re.search(r'\[.*\]', raw, _re.DOTALL)
        generated = json.loads(m.group(0)) if m else []
        generated = [str(q) for q in generated if str(q).strip()]
    except Exception as e:
        logger.warning(f"Query generation failed ({e}) — using keyword fallback")
        generated = [f"{kw} 2026 call for papers" for kw in keywords[:n]]

    # Interleave: curated first (highest signal), then generated.
    seen: set[str] = set()
    out: list[str] = []
    for q in _CURATED_QUERIES + generated:
        key = q.lower().strip()
        if key in seen:
            continue
        seen.add(key)
        out.append(q)
    return out


def run_agent(
    thesis_keywords: list[str],
    thesis_abstract: str,
    dry_run: bool = False,
) -> AgentRunResult:
    """
    Main ReAct loop.
    dry_run=True: finds conferences but skips Google Calendar writes.
    """
    # Truncate abstract to 3 sentences — keeps LLM prompt slim
    sentences = thesis_abstract.split(". ")
    summary = ". ".join(sentences[:3]).strip()
    if not summary.endswith("."):
        summary += "."

    state = AgentState(
        thesis_keywords=thesis_keywords,
        thesis_abstract_summary=summary,
        seen_acronyms=set(),  # no cross-run dedup — always show all conferences
    )

    total_candidates = 0
    dedup_skipped    = 0

    # ── Stage 0: pull from curated aggregators (ai-deadlines, dm-deadlines) ──
    # These give us 50-100 conferences with dates already structured. Still
    # need Haiku to score relevance, but skip the unreliable scrape step.
    logger.info("Fetching curated conference aggregators...")
    aggregator_raw = fetch_aggregator_candidates(min_year=2026)
    aggregator_candidates: list[dict] = []
    seen_in_run: set[str] = set()
    for c in aggregator_raw:
        full_key = f"{c['acronym'].upper()}{c['year']}"
        if full_key in state.seen_acronyms or full_key in seen_in_run:
            dedup_skipped += 1
            continue
        seen_in_run.add(full_key)
        aggregator_candidates.append(c)

    if aggregator_candidates:
        total_candidates += len(aggregator_candidates)
        logger.info(f"  scoring {len(aggregator_candidates)} aggregator candidates")
        scored = batch_score_conferences(
            aggregator_candidates, thesis_keywords, summary, state.seen_acronyms
        )
        logger.info(f"  {len(scored)} passed relevance threshold")
        for conf in scored:
            key = f"{conf.acronym.upper()}{conf.year}"
            if key not in state.seen_acronyms:
                state.found_conferences.append(conf)
                state.seen_acronyms.add(key)

    # If we already have enough from the aggregator, skip the search loop.
    if len(state.found_conferences) >= MIN_CONFERENCES:
        logger.info(f"Aggregator alone yielded {len(state.found_conferences)} — skipping search loop")
        query_queue: list[str] = []
    else:
        logger.info("Generating search queries (1 API call)...")
        query_queue = _generate_queries(thesis_keywords, summary)

    consecutive_empty  = 0

    for i in range(MAX_ITERATIONS):
        state.iteration = i + 1
        if not query_queue:
            logger.info("Query queue exhausted — stopping.")
            break

        batch = query_queue[:QUERIES_PER_ITERATION]
        query_queue = query_queue[QUERIES_PER_ITERATION:]
        state.queries_tried.extend(batch)
        logger.info(f"\n[Iter {state.iteration}/{MAX_ITERATIONS}] {batch}")

        # ── WikiCFP scrape (free, no LLM) ────────────────────────────────────
        raw_candidates: list[dict] = []
        for q in batch:
            short_q = " ".join(
                w for w in q.split()
                if w.lower() not in _STOPWORDS
            )[:40]
            raw_candidates.extend(search_wikicfp(short_q))

        # ── DuckDuckGo Search (free, lru_cache prevents duplicate calls) ────
        import re as _re
        # Match real conference acronyms: 2-8 uppercase letters, NOT a common
        # English title word. Optionally followed by a year, optionally with a
        # leading "ECML-" / "ECML/" style separator.
        _CONF_ACRONYM_RE = _re.compile(r'\b([A-Z]{2,8}(?:[-/][A-Z]{2,8})?)\b')
        # Words that look like acronyms but aren't (English title words / month
        # abbreviations / common page noise).
        _BAD_ACRONYMS = {
            "CFP", "CALL", "FOR", "PAPERS", "PAPER", "THE", "AND", "WITH",
            "INTERNATIONAL", "INTERNATIONA", "CONFERENCE", "WORKSHOP", "DEADLINE",
            "ABSTRACT", "FULL", "JAN", "FEB", "MAR", "APR", "MAY", "JUN",
            "JUL", "AUG", "SEP", "OCT", "NOV", "DEC", "PDF", "HTML", "ACM",
            "IEEE",  # too generic on its own — paired with conf name usually
            "USA", "UK", "EU", "UAE",
        }

        def _pick_acronym(text: str, q: str) -> str:
            for m in _CONF_ACRONYM_RE.finditer(text):
                cand = m.group(1).upper()
                if cand not in _BAD_ACRONYMS and not cand.isdigit():
                    return cand[:15]
            # Fallback: pull the acronym out of the search query itself
            # ("ICDM 2026 call for papers..." → "ICDM")
            for tok in q.split():
                tok_u = tok.upper().rstrip(":,.")
                if (2 <= len(tok_u) <= 8 and tok_u.isalpha()
                        and tok_u.isupper() and tok_u not in _BAD_ACRONYMS):
                    return tok_u
            return "UNK"

        for q in batch:
            for r in ddg_search(q, count=5):
                title = r["title"] or ""
                url = r["url"]
                # Skip junk URLs (blogs, youtube, linkedin, etc.) outright.
                if not is_scrapable_url(url):
                    continue
                acronym = _pick_acronym(title, q)
                if acronym == "UNK":
                    continue  # no real acronym → not a real conference candidate

                dates = extract_from_search_result(title, r["snippet"], url)

                raw_candidates.append({
                    "acronym":  acronym,
                    "name":     title[:150],
                    "url":      url,
                    "conference_date": dates.get("conference_date"),
                    "abstract_deadline": dates.get("abstract_deadline"),
                    "full_paper_deadline": dates.get("full_paper_deadline"),
                    "camera_ready_deadline": dates.get("camera_ready_deadline"),
                    "deadline": r["snippet"][:100],
                    "when": "", "where": "",
                })

        # ── Dedup before sending to LLM (zero extra tokens) ──────────────────
        seen_in_batch: set[str] = set()
        unique: list[dict] = []
        for c in raw_candidates:
            key = c.get("acronym", "").upper().strip()[:12]
            year = "2026"
            for word in (c.get("when","") + " " + c.get("deadline","")).split():
                if word.isdigit() and len(word) == 4:
                    year = word
                    break
            full_key = f"{key}{year}"
            if key and full_key not in seen_in_batch \
                    and full_key not in state.seen_acronyms:
                seen_in_batch.add(full_key)
                unique.append(c)
            else:
                dedup_skipped += 1

        total_candidates += len(unique)
        logger.info(f"  {len(unique)} unique candidates ({dedup_skipped} deduped total)")

        # Pre-filter: only send candidates that have AT LEAST one date to Haiku.
        # The system prompt instructs Haiku to skip null-date entries — sending
        # them anyway wastes tokens and occasionally makes Haiku reply with
        # prose ("All N candidates have null values...") that breaks the parser.
        with_dates = [
            c for c in unique
            if c.get("abstract_deadline") or c.get("full_paper_deadline")
            or c.get("camera_ready_deadline") or c.get("conference_date")
        ]
        if len(with_dates) < len(unique):
            logger.info(f"  {len(unique) - len(with_dates)} dropped (no extractable dates)")

        if not with_dates:
            consecutive_empty += 1
            if consecutive_empty >= MAX_EMPTY_ITERATIONS:
                logger.info(f"  {MAX_EMPTY_ITERATIONS} empty iters — stopping early.")
                break
            continue
        consecutive_empty = 0

        # ── ONE Haiku call scores all candidates in this iteration ────────────
        scored = batch_score_conferences(
            with_dates, thesis_keywords, summary, state.seen_acronyms
        )
        logger.info(f"  {len(scored)} passed relevance threshold")

        for conf in scored:
            key = f"{conf.acronym.upper()}{conf.year}"
            if key not in state.seen_acronyms:
                state.found_conferences.append(conf)
                state.seen_acronyms.add(key)

        if len(state.found_conferences) >= MIN_CONFERENCES:
            logger.info(f"  Reached {MIN_CONFERENCES} conferences — stopping early.")
            break

    # ── Send email report ─────────────────────────────────────────────────────
    sorted_confs = sorted(
        state.found_conferences, key=lambda c: c.relevance_score, reverse=True
    )
    conferences_added = len(sorted_confs)

    if dry_run:
        for conf in sorted_confs:
            logger.info(f"  [DRY RUN] {conf.acronym} {conf.year} "
                        f"score={conf.relevance_score} "
                        f"deadline={conf.full_paper_deadline}")
    else:
        if sorted_confs:
            if not EMAIL_APP_PASSWORD:
                logger.error("EMAIL_APP_PASSWORD not set — skipping email. Add it to .env")
            else:
                try:
                    send_conference_email(sorted_confs, EMAIL_TO, EMAIL_FROM, EMAIL_APP_PASSWORD)
                except Exception as e:
                    logger.error(f"Email send failed: {e}")

    # ── Final cost report ─────────────────────────────────────────────────────
    in_tok, out_tok = get_total_tokens()
    cost = estimate_cost(in_tok, out_tok)
    if not dry_run:
        record_run(conferences_added, cost)

    logger.info(f"\nTokens: {in_tok} in / {out_tok} out — cost ≈ ${cost}")

    return AgentRunResult(
        conferences_added=conferences_added,
        conferences_skipped_dedup=dedup_skipped,
        total_candidates_evaluated=total_candidates,
        iterations_used=state.iteration,
        estimated_cost_usd=cost,
        top_conferences=sorted_confs[:5],
    )
