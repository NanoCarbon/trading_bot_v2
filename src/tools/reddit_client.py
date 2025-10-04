# src/tools/reddit_client.py
import os
import re
import time
from dataclasses import dataclass
from typing import Iterable, List, Optional, Dict

import praw
from dotenv import load_dotenv

load_dotenv()
DEBUG = os.getenv("REDDIT_DEBUG", "0") == "1"

@dataclass
class RedditComment:
    id: str
    subreddit: str
    author: Optional[str]
    body: str
    score: int
    created_utc: float
    permalink: str

def _build_ticker_regex(ticker: str, synonyms: Optional[List[str]] = None) -> re.Pattern:
    t = re.escape(ticker.upper())
    parts = [rf"\${t}", rf"\b{t}\b"]
    for s in (synonyms or []):
        parts.append(rf"\b{re.escape(s)}\b")
    return re.compile("|".join(parts), re.IGNORECASE)

def reddit_readonly() -> praw.Reddit:
    return praw.Reddit(
        client_id=os.getenv("REDDIT_CLIENT_ID"),
        client_secret=os.getenv("REDDIT_SECRET"),
        user_agent=os.getenv("REDDIT_USER_AGENT", "windows:trading-bot:v0.1 (by u/yourname)"),
        check_for_async=False,
    )

def fetch_recent_comments_for_ticker(
    ticker: str,
    subreddits: Iterable[str],
    limit_per_sub: int = 100,
    max_age_days: float = 7.0,
    synonyms: Optional[List[str]] = None,
) -> List[RedditComment]:
    r = reddit_readonly()
    pattern = _build_ticker_regex(ticker, synonyms)
    cutoff = time.time() - max_age_days * 86400

    subs_list = list(subreddits)
    if DEBUG:
        print(f"[reddit] scanning subs={subs_list} ticker={ticker} cutoff_age_days={max_age_days}")

    out: Dict[str, RedditComment] = {}
    for sr in subs_list:
        try:
            for c in r.subreddit(sr).comments(limit=limit_per_sub):
                if getattr(c, "created_utc", 0) < cutoff:
                    continue
                body = getattr(c, "body", "") or ""
                if not pattern.search(body):
                    continue
                rc = RedditComment(
                    id=str(c.id),
                    subreddit=str(c.subreddit),
                    author=None if c.author is None else str(c.author),
                    body=body,
                    score=int(getattr(c, "score", 0) or 0),
                    created_utc=float(getattr(c, "created_utc", 0.0) or 0.0),
                    permalink=f"https://www.reddit.com{getattr(c, 'permalink', '')}",
                )
                if DEBUG:
                    print(f"[reddit] match r/{rc.subreddit}: id={rc.id} score={rc.score} ts={rc.created_utc} preview={rc.body[:80]!r}")
                out[rc.id] = rc
        except Exception as e:
            if DEBUG:
                print(f"[reddit] error scanning r/{sr}: {e!r}")
            continue

    matched = sorted(out.values(), key=lambda x: x.created_utc, reverse=True)
    if DEBUG:
        print(f"[reddit] total matched={len(matched)}")
        if matched:
            print(f"[reddit] first few ids={[m.id for m in matched[:5]]}")
    return matched
