import time
import logging
import httpx
from bs4 import BeautifulSoup
from agent.config import WIKICFP_BASE, WIKICFP_HEADERS, SCRAPE_DELAY_S

logger = logging.getLogger(__name__)

# Module-level flag: once we know wikicfp is unreachable, stop trying for the
# rest of this process. Keeps the logs readable.
_WIKICFP_UNREACHABLE = False


def search_wikicfp(keyword: str) -> list[dict]:
    """
    Scrapes WikiCFP for keyword. No LLM involved — pure structured extraction.
    Silently no-ops once we've detected the host is unreachable.
    """
    global _WIKICFP_UNREACHABLE
    if _WIKICFP_UNREACHABLE:
        return []
    params = {"q": keyword, "year": "f"}
    try:
        resp = httpx.get(WIKICFP_BASE, params=params,
                         headers=WIKICFP_HEADERS, timeout=15)
        resp.raise_for_status()
    except Exception as e:
        # Network unreachable / DNS failure → flip the kill switch so we don't
        # hammer the box with 15 identical errors per run.
        msg = str(e).lower()
        if "unreachable" in msg or "name or service" in msg or "timed out" in msg:
            _WIKICFP_UNREACHABLE = True
            logger.info("  [wikicfp] host unreachable — disabling for this run")
        else:
            logger.debug(f"  [wikicfp] error for '{keyword}': {e}")
        return []

    time.sleep(SCRAPE_DELAY_S)
    soup = BeautifulSoup(resp.text, "html.parser")
    results = []

    for row in soup.select("table.gglu tr")[1:]:
        cols = row.find_all("td")
        if len(cols) < 5:
            continue
        link = cols[0].find("a")
        results.append({
            "acronym":  cols[0].get_text(strip=True)[:20],
            "name":     cols[1].get_text(strip=True)[:200],
            "when":     cols[2].get_text(strip=True),
            "where":    cols[3].get_text(strip=True),
            "deadline": cols[4].get_text(strip=True),
            "url": ("https://www.wikicfp.com" + link["href"]) if link else "",
        })
    return results
