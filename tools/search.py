from functools import lru_cache
from ddgs import DDGS

@lru_cache(maxsize=64)
def ddg_search(query: str, count: int = 5) -> tuple:
    """
    DuckDuckGo search with lru_cache — identical query in same run = zero extra calls.
    Returns a tuple (hashable) of result dicts.
    """
    try:
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=count))
        return tuple(
            {"title": r.get("title", ""), "url": r.get("href", ""), "snippet": r.get("body", "")}
            for r in results
        )
    except Exception as e:
        print(f"  [search] DuckDuckGo error: {e}")
        return tuple()
