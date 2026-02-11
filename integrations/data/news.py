"""News aggregation from Tavily and Alpaca News API."""

from __future__ import annotations

import os
from typing import Any

import httpx
from dotenv import load_dotenv
from tavily import TavilyClient

from utils.logging import get_logger

load_dotenv()
log = get_logger(__name__)


def search_tavily(
    tavily: TavilyClient | None,
    *,
    query: str,
    topic: str = "news",
    days: int = 7,
    max_results: int = 5,
) -> list[dict[str, Any]]:
    """Search news via Tavily."""
    if tavily is None:
        return []

    log.info("Tavily news search: %s", query)
    res = tavily.search(
        query=query,
        topic=topic,
        days=days,
        max_results=max_results,
        search_depth="basic",
    )
    results = res.get("results", []) or []
    return [
        {
            "title": r.get("title", ""),
            "url": r.get("url", ""),
            "content": r.get("content", "")[:500],
            "score": r.get("score"),
            "source": "tavily",
        }
        for r in results
        if isinstance(r, dict)
    ]


def search_alpaca_news(
    symbols: list[str],
    *,
    limit: int = 10,
) -> list[dict[str, Any]]:
    """Search news via Alpaca News API (data API v2)."""
    api_key = os.environ.get("ALPACA_KEY")
    api_secret = os.environ.get("ALPACA_SECRET")
    if not api_key or not api_secret:
        return []

    url = "https://data.alpaca.markets/v1beta1/news"
    headers = {
        "Apca-Api-Key-Id": api_key,
        "Apca-Api-Secret-Key": api_secret,
    }
    params = {
        "symbols": ",".join(symbols),
        "limit": limit,
        "sort": "desc",
    }

    log.info("Alpaca news: symbols=%s limit=%d", symbols, limit)
    try:
        r = httpx.get(url, headers=headers, params=params, timeout=15.0)
        r.raise_for_status()
        data = r.json()
        news_items = data.get("news", [])
        return [
            {
                "title": item.get("headline", ""),
                "url": item.get("url", ""),
                "content": item.get("summary", "")[:500],
                "symbols": item.get("symbols", []),
                "created_at": item.get("created_at"),
                "source": "alpaca",
            }
            for item in news_items
        ]
    except Exception as e:
        log.error("Alpaca news error: %s", e)
        return []


def aggregate_news(
    tavily: TavilyClient | None,
    symbols: list[str],
    *,
    keywords: list[str] | None = None,
    max_results: int = 10,
) -> list[dict[str, Any]]:
    """Aggregate news from all sources, optionally filtered by keywords."""
    results: list[dict[str, Any]] = []

    # Tavily search
    for symbol in symbols[:3]:  # limit to avoid rate limits
        query = f"{symbol} stock news"
        if keywords:
            query += " " + " ".join(keywords[:3])
        results.extend(search_tavily(tavily, query=query, max_results=max_results // 2))

    # Alpaca news
    results.extend(search_alpaca_news(symbols, limit=max_results))

    # Filter by keywords if provided
    if keywords:
        kw_lower = [k.lower() for k in keywords]
        results = [
            r for r in results
            if any(
                kw in r.get("title", "").lower() or kw in r.get("content", "").lower()
                for kw in kw_lower
            )
        ]

    return results[:max_results]
