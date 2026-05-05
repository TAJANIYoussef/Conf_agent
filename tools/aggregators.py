"""
Curated conference aggregator sources.

Far more reliable than DDG search + page scraping because the data is
structured by hand and includes deadlines, dates, places, and topics.

Primary sources:
- ai-deadlines (https://aideadlin.es) — community-maintained YAML
- dm-deadlines (https://dm-deadlines.github.io) — data mining focus

Both expose their data as YAML files in public GitHub repos. We fetch the
raw file, parse, and filter for relevant subjects.
"""
from __future__ import annotations

import logging
import re
from datetime import date, datetime
from typing import Iterable, Optional

import httpx
import yaml

logger = logging.getLogger(__name__)

# Raw YAML feeds — pinned to master/main branches of the upstream repos.
AGGREGATOR_FEEDS = [
    "https://raw.githubusercontent.com/abhshkdz/ai-deadlines/master/_data/conferences.yml",
    "https://raw.githubusercontent.com/dm-deadlines/dm-deadlines.github.io/master/_data/conferences.yml",
]

# Subject filters — only relevant ML/DM tracks. Drop CV/NLP/RO/SP/HCI.
RELEVANT_SUBS = {"ML", "DM", "KR", "AP"}

_TZ_SUFFIX_RE = re.compile(
    r"\s*\(?(AoE|UTC|GMT|PST|PT|EST|ET|CET|CEST|JST|KST|BST|EDT|PDT)[^\)]*\)?\s*$",
    re.IGNORECASE,
)


def _parse_iso_datetime(value) -> Optional[date]:
    """Aggregator deadlines are ISO strings like '2026-05-22 20:00:00'."""
    if value is None:
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    s = str(value).strip()
    if not s or s.lower() == "tba":
        return None
    s = _TZ_SUFFIX_RE.sub("", s).strip()
    for fmt in (
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d",
        "%Y/%m/%d",
        "%Y-%m-%dT%H:%M:%S",
    ):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def _normalize(entry: dict) -> Optional[dict]:
    """Convert one YAML entry into our internal candidate dict."""
    title = entry.get("title") or ""
    year = entry.get("year")
    if not title or not year:
        return None
    sub = entry.get("sub") or ""
    if sub and sub not in RELEVANT_SUBS:
        return None

    full_paper = _parse_iso_datetime(entry.get("deadline"))
    abstract = _parse_iso_datetime(entry.get("abstract_deadline"))
    start = _parse_iso_datetime(entry.get("start"))

    if not (full_paper or abstract or start):
        return None

    # Build a stable, human readable name
    full_name = entry.get("full_name") or title
    name = f"{full_name} ({title} {year})" if full_name != title else f"{title} {year}"

    return {
        "acronym": str(title).upper().strip()[:15],
        "name": name[:200],
        "url": entry.get("link") or entry.get("hindex_url") or "",
        "conference_date": start,
        "abstract_deadline": abstract,
        "full_paper_deadline": full_paper,
        "camera_ready_deadline": None,  # aggregators rarely list this
        "year": int(year),
        "venue": entry.get("place") or entry.get("location") or "",
        "deadline": "",
        "when": "",
        "where": "",
        "_source": "aggregator",
    }


def _fetch_feed(url: str, timeout: int = 15) -> list[dict]:
    try:
        resp = httpx.get(url, timeout=timeout, follow_redirects=True)
        resp.raise_for_status()
    except Exception as e:
        logger.info(f"  [aggregator] {url.split('/')[-3]} unreachable: {e}")
        return []
    try:
        data = yaml.safe_load(resp.text) or []
    except Exception as e:
        logger.warning(f"  [aggregator] YAML parse failed for {url}: {e}")
        return []
    if not isinstance(data, list):
        return []
    return data


def fetch_aggregator_candidates(min_year: int = 2025) -> list[dict]:
    """
    Pull all aggregator feeds, normalize, keep candidates that have at least
    one date in the future (regardless of nominal `year` field — community
    YAMLs sometimes lag behind for next-year editions).
    """
    out: list[dict] = []
    seen_keys: set[str] = set()
    today = date.today()
    rejected_year = rejected_past = 0

    for feed_url in AGGREGATOR_FEEDS:
        raw = _fetch_feed(feed_url)
        for entry in raw:
            if not isinstance(entry, dict):
                continue
            try:
                cand = _normalize(entry)
            except Exception:
                continue
            if not cand:
                continue
            if cand["year"] < min_year:
                rejected_year += 1
                continue

            # Keep if any deadline OR conference date is today-or-later.
            future_dates = [
                d for d in (
                    cand["abstract_deadline"],
                    cand["full_paper_deadline"],
                    cand["camera_ready_deadline"],
                    cand["conference_date"],
                ) if d and d >= today
            ]
            if not future_dates:
                rejected_past += 1
                continue

            key = f"{cand['acronym']}{cand['year']}"
            if key in seen_keys:
                continue
            seen_keys.add(key)
            out.append(cand)

    logger.info(
        f"  [aggregator] {len(out)} candidates "
        f"(rejected: {rejected_year} old-year, {rejected_past} all-past-dates)"
    )
    return out
