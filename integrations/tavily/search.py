import json
from typing import Literal

from tavily import TavilyClient

from utils.logging import get_logger

log = get_logger(__name__)


def web_search(
    tavily: TavilyClient,
    *,
    query: str,
    topic: Literal["general", "news", "finance"] = "news",
    days: int = 7,
    max_results: int = 5,
) -> dict:
    log.info(
        "Tavily web_search: query=%r topic=%s days=%s max_results=%s",
        query,
        topic,
        days,
        max_results,
    )

    res = tavily.search(
        query=query,
        topic=topic,
        days=days,
        max_results=max_results,
        search_depth="basic",
    )

    results = res.get("results", []) or []
    urls = [r.get("url") for r in results[:5] if isinstance(r, dict)]
    log.info("Tavily web_search: results=%s urls=%s", len(results), urls)

    log.info("Tavily web_search output=%s", json.dumps(res, ensure_ascii=False))

    return res
