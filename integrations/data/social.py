"""Social sentiment from Reddit (PRAW) and StockTwits."""

from __future__ import annotations

import os
from typing import Any

import httpx
from dotenv import load_dotenv

from utils.logging import get_logger

load_dotenv()
log = get_logger(__name__)


def search_reddit(
    keywords: list[str],
    *,
    subreddits: list[str] | None = None,
    limit: int = 25,
) -> list[dict[str, Any]]:
    """Search Reddit for keyword mentions using PRAW.

    Returns list of posts with title, score, comments, and subreddit.
    """
    client_id = os.environ.get("REDDIT_CLIENT_ID")
    client_secret = os.environ.get("REDDIT_CLIENT_SECRET")
    user_agent = os.environ.get("REDDIT_USER_AGENT", "swing-trader/0.2.0")

    if not client_id or not client_secret:
        log.info("Reddit credentials not configured, skipping")
        return []

    try:
        import praw

        reddit = praw.Reddit(
            client_id=client_id,
            client_secret=client_secret,
            user_agent=user_agent,
        )

        subs = subreddits or ["wallstreetbets", "stocks", "options", "investing"]
        sub_str = "+".join(subs)
        query = " OR ".join(keywords)

        log.info("Reddit search: %s in r/%s", query, sub_str)
        posts = []
        for submission in reddit.subreddit(sub_str).search(query, limit=limit, sort="new"):
            posts.append({
                "title": submission.title,
                "score": submission.score,
                "num_comments": submission.num_comments,
                "subreddit": str(submission.subreddit),
                "url": f"https://reddit.com{submission.permalink}",
                "created_utc": submission.created_utc,
                "source": "reddit",
            })

        log.info("Reddit: found %d posts", len(posts))
        return posts

    except ImportError:
        log.error("PRAW not installed")
        return []
    except Exception as e:
        log.error("Reddit error: %s", e)
        return []


def search_stocktwits(symbol: str, *, limit: int = 20) -> list[dict[str, Any]]:
    """Get recent StockTwits messages for a symbol.

    Uses the public API (no auth required, rate limited).
    """
    url = f"https://api.stocktwits.com/api/2/streams/symbol/{symbol}.json"
    log.info("StockTwits search: %s", symbol)

    try:
        r = httpx.get(url, timeout=10.0)
        r.raise_for_status()
        data = r.json()

        messages = data.get("messages", [])[:limit]
        results = []
        for msg in messages:
            sentiment = None
            if msg.get("entities", {}).get("sentiment"):
                sentiment = msg["entities"]["sentiment"].get("basic")
            results.append({
                "body": msg.get("body", "")[:300],
                "sentiment": sentiment,
                "created_at": msg.get("created_at"),
                "likes": msg.get("likes", {}).get("total", 0),
                "source": "stocktwits",
            })

        # Compute sentiment breakdown
        bullish = sum(1 for r in results if r["sentiment"] == "Bullish")
        bearish = sum(1 for r in results if r["sentiment"] == "Bearish")
        total = bullish + bearish

        return {
            "symbol": symbol,
            "messages": results,
            "count": len(results),
            "bullish": bullish,
            "bearish": bearish,
            "sentiment_ratio": bullish / total if total > 0 else None,
        }

    except Exception as e:
        log.error("StockTwits error: %s", e)
        return {"symbol": symbol, "messages": [], "count": 0, "error": str(e)}


def aggregate_social(
    symbols: list[str],
    *,
    subreddits: list[str] | None = None,
) -> dict[str, Any]:
    """Aggregate social signals for multiple symbols."""
    result = {}

    for symbol in symbols[:5]:  # limit to avoid rate limits
        ticker = symbol.replace("/", "").replace("USD", "")
        reddit_posts = search_reddit([ticker, symbol], subreddits=subreddits)
        stocktwits = search_stocktwits(ticker)

        result[symbol] = {
            "reddit_mentions": len(reddit_posts),
            "reddit_avg_score": (
                sum(p.get("score", 0) for p in reddit_posts) / len(reddit_posts)
                if reddit_posts else 0
            ),
            "stocktwits": stocktwits,
        }

    return result
