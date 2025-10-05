# src/pillars/sentiment/twitter_sentiment.py
from __future__ import annotations

from typing import List, Dict
from datetime import datetime
import math

import nltk
from nltk.sentiment import SentimentIntensityAnalyzer

from src.tools.twitter_client import TwitterClient, RateLimitedError


class TwitterSentimentTool:
    """
    Returns a stable vote record so the collector never AttributeErrors.

    Return schema (always):
    {
      "pillar": "sentiment",
      "source": "twitter",
      "vote": "BUY" | "HOLD" | "SELL",
      "score": float,          # avg VADER compound in [-1, 1]
      "confidence": float,     # 0..1 derived from |score|
      "meta": {                # safe, informative
        "used_query": str,
        "n_texts": int,
        "reason": str | None,  # e.g., 'rate_limited', 'no_tweets', 'error:...'
        "detail": dict | None  # small, safe details (reset time, etc.)
      }
    }
    """

    def __init__(self, debug: bool = False) -> None:
        self.client = TwitterClient(debug=debug)
        self.sia = self._init_sia()
        self.debug = debug

    # ---------- internals ----------

    def _init_sia(self) -> SentimentIntensityAnalyzer:
        try:
            nltk.data.find("sentiment/vader_lexicon.zip")
        except LookupError:
            nltk.download("vader_lexicon", quiet=True)
        return SentimentIntensityAnalyzer()

    def _label(self, score: float) -> str:
        if score >= 0.05:
            return "BUY"
        if score <= -0.05:
            return "SELL"
        return "HOLD"

    def _confidence(self, score: float) -> float:
        """
        Map |compound| in [0,1] to a soft confidence in [0.5, 0.95].
        Keeps a floor so the UI never shows 0.0 when we do have a signal.
        """
        mag = min(1.0, abs(score))
        return round(0.5 + 0.45 * mag, 2)

    def _candidate_queries(self, ticker: str) -> List[str]:
        return [
            f"(cashtags:{ticker} OR ${ticker} OR {ticker}) lang:en -is:retweet -is:reply",
            f"(cashtags:{ticker} OR ${ticker} OR {ticker}) lang:en -is:retweet",
            f"{ticker} lang:en -is:retweet",
        ]

    def _empty_result(self, reason: str | None = None, detail: dict | None = None, used_query: str = "", n_texts: int = 0) -> Dict:
        return {
            "pillar": "sentiment",
            "source": "twitter",
            "vote": "HOLD",
            "score": 0.0,
            "confidence": 0.50,
            "meta": {
                "used_query": used_query,
                "n_texts": int(n_texts),
                "reason": reason,
                "detail": detail or None,
            },
        }

    # ---------- public API ----------

    def fetch_and_score(self, ticker: str, limit: int = 10) -> Dict:
        tweet_fields = ["created_at", "lang", "public_metrics"]
        used_query = ""
        tweets: List[str] = []

        try:
            for q in self._candidate_queries(ticker):
                used_query = q
                tweets.clear()

                # Twitter requires max_results >= 10; we process only the first text to be gentle.
                page = self.client.search_recent_tweets(query=q, max_results=max(10, min(100, limit)))
                for t in page.get("data", []) or []:
                    text = (t.get("text") or "").replace("\n", " ").strip()
                    if text:
                        tweets.append(text)
                    if len(tweets) >= 1:
                        break

                if tweets:
                    break

            if not tweets:
                # Clean HOLD result with reason
                return self._empty_result(reason="no_tweets", used_query=used_query, n_texts=0)

            # Score the one (or few) texts we grabbed
            scores = [self.sia.polarity_scores(t)["compound"] for t in tweets]
            avg_score = sum(scores) / len(scores) if scores else 0.0
            vote = self._label(avg_score)
            conf = self._confidence(avg_score)

            if self.debug:
                sample = tweets[0][:160]
                print(f"[twitter_sentiment] used_query={used_query} n={len(tweets)} avg={avg_score:+.3f} conf={conf} ex={sample!r}")

            return {
                "pillar": "sentiment",
                "source": "twitter",
                "vote": vote,
                "score": float(round(avg_score, 4)),
                "confidence": float(conf),
                "meta": {
                    "used_query": used_query,
                    "n_texts": int(len(tweets)),
                    "reason": None,
                    "detail": None,
                },
            }

        except RateLimitedError as rl:
            reset_iso = None
            if rl.reset_epoch:
                reset_iso = datetime.utcfromtimestamp(rl.reset_epoch).isoformat() + "Z"
            return self._empty_result(
                reason="rate_limited",
                used_query=used_query,
                detail={
                    "limit": rl.limit,
                    "remaining": rl.remaining,
                    "reset_epoch": rl.reset_epoch,
                    "reset_utc": reset_iso,
                },
                n_texts=0,
            )

        except Exception as e:
            # Any unexpected error → stable HOLD shape with reason and detail.
            return self._empty_result(
                reason=f"error:{type(e).__name__}",
                detail={"message": str(e)[:300]},
                used_query=used_query,
                n_texts=0,
            )
