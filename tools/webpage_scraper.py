import re
import logging
from datetime import date, datetime
from typing import Optional, Dict, List
import httpx
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

# Match the year as a free-floating capture group to allow stricter validation.
DATE_PATTERNS = [
    r'(\d{4}[-/]\d{1,2}[-/]\d{1,2})',                 # 2026-05-22 / 2026/05/22
    r'(\d{1,2}[-/]\d{1,2}[-/]\d{4})',                 # 22-05-2026 / 5/22/2026
    r'([A-Z][a-z]+\.?\s+\d{1,2}(?:st|nd|rd|th)?,?\s+\d{4})',   # May 22(nd), 2026
    r'(\d{1,2}(?:st|nd|rd|th)?\s+[A-Z][a-z]+\.?\s+\d{4})',     # 22nd May 2026
]

# Keywords for each deadline type. Lowercased substring matching.
DEADLINE_KEYWORDS = {
    'abstract_deadline': [
        'abstract deadline', 'abstract submission', 'abstract due',
        'abstract registration', 'abstract close', 'abstract cut-off',
        'short paper deadline', 'title and abstract',
    ],
    'full_paper_deadline': [
        'paper deadline', 'paper submission', 'full paper', 'submission deadline',
        'paper due', 'main conference deadline', 'research track deadline',
        'full paper submission', 'submission due', 'manuscript submission',
        'paper registration deadline', 'paper submission deadline',
    ],
    'camera_ready_deadline': [
        'camera ready', 'camera-ready', 'final version', 'final manuscript',
        'camera copy', 'proofs deadline', 'copyright form',
    ],
    'conference_date': [
        'conference date', 'conference dates', 'conference period', 'event date',
        'takes place', 'will be held', 'conference is scheduled', 'dates:',
        'when:', 'where and when', 'main conference',
    ],
}

# Strip trailing timezone / AoE markers before parsing dates.
_TZ_TAIL_RE = re.compile(
    r'\s*(?:\(|\[)?\s*(?:AoE|UTC|GMT|PST|PT|EST|ET|CET|CEST|JST|KST|BST|EDT|PDT|AEST)'
    r'[^,;\n]*$',
    re.IGNORECASE,
)
_TIME_RE = re.compile(r'\s+\d{1,2}:\d{2}(?::\d{2})?\s*$')

# Headings worth opening; signal an "Important Dates" block.
_DATES_HEADING_RE = re.compile(
    r'\b(important dates|key dates|deadlines?|schedule|timeline|submission)\b',
    re.IGNORECASE,
)

# Domains that almost never host a real CFP page. Skip scraping outright.
SKIP_DOMAINS = {
    "youtube.com", "www.youtube.com", "youtu.be",
    "linkedin.com", "www.linkedin.com",
    "github.com", "www.github.com",
    "kaggle.com", "www.kaggle.com",
    "fast.ai", "www.fast.ai",
    "researchgate.net", "www.researchgate.net",
    "academia.edu", "www.academia.edu",
    "reddit.com", "www.reddit.com",
    "medium.com", "dev.to",
    "stackoverflow.com", "stackexchange.com",
    "amazon.com", "amazon.in",
    "facebook.com", "twitter.com", "x.com",
    "ibm.com", "google.com",
    "wikipedia.org", "en.wikipedia.org",
    "freedium-mirror.cfd",
    "cfp.net", "www.cfp.net",  # certified financial planner — false positive
    "dalton-education.com",
    "bostonifi.com",
}

# Path fragments that indicate non-conference content (independent of domain).
SKIP_PATH_FRAGMENTS = (
    "/blog/", "/news/", "/post/", "/posts/", "/topics/",
    "/article/", "/articles/", "/publication/",
    "/video/", "/watch", "/profile/",
    "/pdf/", ".pdf",
    "/glossary", "/tutorial",
)

# Path fragments that are STRONG positive signals — always allow scraping.
ALLOW_PATH_FRAGMENTS = (
    "cfp", "call-for-papers", "callforpapers", "call_for_papers",
    "submission", "submissions", "important-dates", "dates",
    "deadlines",
)


def is_scrapable_url(url: str) -> bool:
    """Quick allow/deny heuristic before paying the network round-trip."""
    if not url or not url.startswith(("http://", "https://")):
        return False
    try:
        from urllib.parse import urlparse
        p = urlparse(url)
    except Exception:
        return False
    host = (p.hostname or "").lower()
    if host in SKIP_DOMAINS:
        return False
    path = p.path.lower()
    # Strong positive signal — always scrape regardless of domain.
    if any(frag in path for frag in ALLOW_PATH_FRAGMENTS):
        return True
    # Drop obvious non-conference content paths.
    if any(frag in path for frag in SKIP_PATH_FRAGMENTS):
        return False
    return True


def _normalize_date_text(s: str) -> str:
    """Strip ordinal suffixes, trailing times, timezone tails."""
    s = s.strip().rstrip(",")
    s = _TZ_TAIL_RE.sub("", s).strip().rstrip(",")
    s = _TIME_RE.sub("", s).strip()
    s = re.sub(r'(\d{1,2})(st|nd|rd|th)\b', r'\1', s, flags=re.IGNORECASE)
    s = s.replace(".", "")
    return s


def _parse_date(date_str: str) -> Optional[date]:
    if not date_str or not date_str.strip():
        return None
    cleaned = _normalize_date_text(date_str)

    formats = [
        '%Y-%m-%d', '%Y/%m/%d',
        '%d-%m-%Y', '%d/%m/%Y',
        '%m-%d-%Y', '%m/%d/%Y',
        '%B %d, %Y', '%b %d, %Y',
        '%B %d %Y', '%b %d %Y',
        '%d %B %Y', '%d %b %Y',
    ]
    for fmt in formats:
        try:
            return datetime.strptime(cleaned, fmt).date()
        except ValueError:
            continue
    return None


def _find_date_in_text(text: str) -> Optional[date]:
    """Return the first parseable date found anywhere in `text`."""
    for pattern in DATE_PATTERNS:
        for match in re.finditer(pattern, text):
            parsed = _parse_date(match.group(1))
            if parsed and 2024 <= parsed.year <= 2030:
                return parsed
    return None


def _matches_keyword(text: str, deadline_type: str) -> bool:
    text_l = text.lower()
    return any(kw in text_l for kw in DEADLINE_KEYWORDS.get(deadline_type, []))


def _extract_from_table(soup: BeautifulSoup, deadline_type: str) -> Optional[date]:
    """
    Search for keyword-bearing cells, then scan adjacent cells for dates.
    Conference tables usually pair a 'label' cell with a 'date' cell.
    """
    cells = soup.find_all(['td', 'th'])
    for i, cell in enumerate(cells):
        if not _matches_keyword(cell.get_text(strip=True), deadline_type):
            continue
        for j in range(i, min(len(cells), i + 4)):
            d = _find_date_in_text(cells[j].get_text(separator=" ", strip=True))
            if d:
                return d
    return None


def _extract_from_dates_section(soup: BeautifulSoup, deadline_type: str) -> Optional[date]:
    """
    Find the 'Important Dates' (or similar) heading, then look at the next
    sibling block (list, table, paragraph) for keyword/date pairs.
    """
    headings = soup.find_all(['h1', 'h2', 'h3', 'h4', 'h5', 'strong', 'b'])
    for h in headings:
        if not _DATES_HEADING_RE.search(h.get_text(" ", strip=True)):
            continue
        chunks: List[str] = []
        for sib in h.find_all_next(limit=80):
            if sib.name and sib.name.startswith("h") and sib is not h:
                break
            text = sib.get_text(" ", strip=True) if sib else ""
            if text:
                chunks.append(text)
        block = "\n".join(chunks)
        for line in block.split("\n"):
            if _matches_keyword(line, deadline_type):
                d = _find_date_in_text(line)
                if d:
                    return d
    return None


def _extract_from_structured_text(text: str, deadline_type: str) -> Optional[date]:
    lines = text.split('\n')
    for idx, line in enumerate(lines):
        if not _matches_keyword(line, deadline_type):
            continue
        window = " ".join(lines[idx:idx + 3])
        d = _find_date_in_text(window)
        if d:
            return d
    return None


def extract_dates_from_html(html: str, url: str = "") -> Dict[str, Optional[date]]:
    result = {
        'conference_date': None,
        'abstract_deadline': None,
        'full_paper_deadline': None,
        'camera_ready_deadline': None,
    }
    try:
        soup = BeautifulSoup(html, 'html.parser')
        for tag in soup(['script', 'style', 'noscript']):
            tag.decompose()
        text = soup.get_text(separator='\n')

        for deadline_type in result.keys():
            d = (
                _extract_from_dates_section(soup, deadline_type)
                or _extract_from_table(soup, deadline_type)
                or _extract_from_structured_text(text, deadline_type)
            )
            if d:
                result[deadline_type] = d
    except Exception as e:
        logger.debug(f"Failed to parse HTML from {url}: {e}")
    return result


def scrape_conference_page(url: str, timeout: int = 10) -> Dict[str, Optional[date]]:
    result = {
        'conference_date': None,
        'abstract_deadline': None,
        'full_paper_deadline': None,
        'camera_ready_deadline': None,
    }
    if not is_scrapable_url(url):
        return result
    try:
        resp = httpx.get(
            url,
            timeout=timeout,
            follow_redirects=True,
            headers={"User-Agent": "Mozilla/5.0 (academic-research-bot/1.0)"},
        )
        resp.raise_for_status()
        result.update(extract_dates_from_html(resp.text, url))
    except Exception as e:
        logger.debug(f"Failed to fetch {url}: {e}")
    return result


def extract_from_search_result(title: str, snippet: str, url: str) -> Dict[str, Optional[date]]:
    """
    Try the snippet (cheap, in-memory) first; if nothing, scrape the page.
    """
    dates = extract_dates_from_html(
        f"<html><body>{title}\n{snippet}</body></html>", url
    )
    if any(dates.values()):
        return dates
    return scrape_conference_page(url)
