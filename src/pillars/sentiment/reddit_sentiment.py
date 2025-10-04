# src/pillars/sentiment/reddit_sentiment.py
from __future__ import annotations

import json
import math
import textwrap
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional

from .interfaces import Vote, SentimentTool
from .utils import exp_decay_weight, clamp01
from ...tools.reddit_client import fetch_recent_comments_for_ticker, RedditComment

from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate



def _score_weight(score: int, min_w: float, max_w: float) -> float:
    """Upvotes give a gentle boost, clamped to [min_w, max_w]."""
    base = 1.0 + math.log1p(max(0, score)) / 3.0
    return float(min(max_w, max(min_w, base)))


def _age_days(ts_utc: float) -> float:
    now = datetime.now(timezone.utc).timestamp()
    return max(0.0, (now - ts_utc) / 86400.0)


class RedditBatchSentimentTool(SentimentTool):
    """
    Fetch recent comments that mention TICKER, classify them in one LLM call,
    then aggregate into a BUY/SELL/HOLD vote using age + score weighting.
    """

    name = "REDDIT_SENTIMENT"
    pillar = "sentiment"

    def _classify_batch(
        self,
        model: str,
        comments: List[RedditComment],
        ticker: str,
    ) -> List[Dict[str, Any]]:
        """
        Returns a list of dicts:
          {"id": <comment_id>, "sentiment": "Bullish|Bearish|Neutral", "confidence": float}
        Order matches input. Falls back to Neutral on parse errors.
        """
        llm = ChatOpenAI(model=model, temperature=0)

        prompt = ChatPromptTemplate.from_template(textwrap.dedent("""
        You are a precise financial sentiment tagger.

        TASK:
        For each comment, return sentiment for the specific ticker {ticker} as one of the ENUM values:
        - "Bullish", "Bearish", or "Neutral".
        If the comment mentions many tickers or is off-topic for {ticker}, choose "Neutral".
        Output MUST be valid JSON: a list of objects with keys:
        - "id": the provided id
        - "sentiment": one of "Bullish" | "Bearish" | "Neutral"
        - "confidence": a float in [0,1] (your internal confidence; optional but recommended)

        EXAMPLE INPUT ITEMS:
        [
        {{ "id": "c1", "body": "$AAPL to the moon, earnings crushed!" }},
        {{ "id": "c2", "body": "I think AAPL is overpriced; margins compressing." }}
        ]

        EXAMPLE OUTPUT:
        [
        {{ "id": "c1", "sentiment": "Bullish", "confidence": 0.8 }},
        {{ "id": "c2", "sentiment": "Bearish", "confidence": 0.7 }}
        ]

        Now classify these comments (array is below). Respond with ONLY the JSON array (no prose):
        {items}
        """).strip())

        items = [{"id": c.id, "body": c.body} for c in comments]
        msg = prompt.format_messages(ticker=ticker, items=json.dumps(items, ensure_ascii=False))
        resp = llm.invoke(msg)
        text = resp.content

        try:
            data = json.loads(text)
            if isinstance(data, list):
                out = []
                allowed = {"Bullish", "Bearish", "Neutral"}
                for row in data:
                    cid = str(row.get("id", ""))
                    sent = str(row.get("sentiment", "Neutral")).strip().title()
                    conf = row.get("confidence", 0.5)
                    if cid and sent in allowed:
                        out.append({"id": cid, "sentiment": sent, "confidence": float(conf)})
                # Preserve input order; default missing ones to Neutral
                by_id = {r["id"]: r for r in out}
                ordered = [
                    by_id.get(c.id, {"id": c.id, "sentiment": "Neutral", "confidence": 0.5})
                    for c in comments
                ]
                return ordered
        except Exception:
            pass

        # fallback: neutral for all
        return [{"id": c.id, "sentiment": "Neutral", "confidence": 0.5} for c in comments]

    def compute(
        self,
        ticker: str,
        *,
        subreddits: List[str],
        synonyms: Optional[List[str]] = None,
        max_comments: int = 50,
        classify_top_n: int = 15,
        half_life_days: float = 3.0,
        min_score_weight: float = 0.5,
        max_score_weight: float = 2.0,
        model: str = "gpt-4o-mini",
        max_age_days: float = 7.0,
        db_con=None,                # optional: sqlite3 connection to log comments
        run_id: Optional[int]=None  # optional: run id to link comment rows
    ) -> Vote:
        # 1) fetch + filter
        all_comments = fetch_recent_comments_for_ticker(
            ticker=ticker,
            subreddits=subreddits,
            limit_per_sub=max_comments,
            max_age_days=max_age_days,
            synonyms=synonyms or [],
        )
        if not all_comments:
            return {
                "pillar": self.pillar, "tool": self.name,
                "signal": "HOLD", "vote": 0, "confidence": 0.5,
                "reason": f"No recent mentions for {ticker}",
                "data": {"ticker": ticker, "counts": {"bull":0,"bear":0,"neu":0}, "weighted_sum": 0.0},
            }

        # newest first -> choose top N to classify
        comments = all_comments[: classify_top_n]

        # 2) classify
        results = self._classify_batch(model=model, comments=comments, ticker=ticker)

        # 3) aggregate with age + score weighting
        enum_map = {"Bullish": 1, "Neutral": 0, "Bearish": -1}
        rows: List[Dict[str, Any]] = []
        weighted_sum = 0.0
        w_denom = 0.0
        counts = {"bull": 0, "bear": 0, "neu": 0}

        for c in comments:
            r = next((x for x in results if x["id"] == c.id), {"sentiment":"Neutral","confidence":0.5})
            s_raw = enum_map.get(r["sentiment"], 0)

            age_w = exp_decay_weight(_age_days(c.created_utc), half_life_days)
            score_w = _score_weight(c.score, min_score_weight, max_score_weight)
            w = float(age_w * score_w)

            weighted_sum += s_raw * w
            w_denom += w

            if s_raw > 0: counts["bull"] += 1
            elif s_raw < 0: counts["bear"] += 1
            else: counts["neu"] += 1

            rows.append({
                "id": c.id,
                "subreddit": c.subreddit,
                "score": c.score,
                "created_utc": c.created_utc,
                "weight": w,
                "sentiment": r["sentiment"],
                "sentiment_score": s_raw,
                "confidence_model": clamp01(r.get("confidence", 0.5)),
                "permalink": c.permalink,
                "preview": c.body[:240],
            })

        # 4) decision
        if abs(weighted_sum) < 1e-9 or w_denom == 0:
            signal, vote = "HOLD", 0
        elif weighted_sum > 0:
            signal, vote = "BUY", 1
        else:
            signal, vote = "SELL", -1

        conf = 0.5 if w_denom == 0 else float(min(0.9, 0.5 + 0.4 * abs(weighted_sum) / w_denom))
        reason = f"Reddit sentiment: bull={counts['bull']} bear={counts['bear']} neu={counts['neu']} (weighted sum={weighted_sum:.2f})"

        # 5) optional: persist per-comment rows if run_id/db_con provided
        if db_con is not None and run_id is not None:
            try:
                by_id = {c.id: c for c in comments}
                db_rows = []
                for r in rows:
                    c = by_id[r["id"]]
                    db_rows.append({
                        "comment_id": r["id"],
                        "subreddit": r["subreddit"],
                        "author": getattr(c, "author", None),
                        "body": getattr(c, "body", ""),
                        "score": r["score"],
                        "created_utc": r["created_utc"],
                        "sentiment": r["sentiment"],
                        "sentiment_score": r["sentiment_score"],
                        "confidence_model": r["confidence_model"],
                        "weight": r["weight"],
                        "permalink": r["permalink"],
                    })
                # relative import back to src/db.py
                from ...db import insert_sentiment_rows
                insert_sentiment_rows(db_con, run_id, ticker, db_rows)
            except Exception:
                # Do not fail the whole vote if logging errors occur
                pass

        return {
            "pillar": self.pillar, "tool": self.name,
            "signal": signal, "vote": vote, "confidence": conf,
            "reason": reason,
            "data": {
                "ticker": ticker,
                "counts": counts,
                "weighted_sum": weighted_sum,
                "w_denom": w_denom,
                "params": {
                    "subreddits": subreddits,
                    "classify_top_n": classify_top_n,
                    "half_life_days": half_life_days,
                    "min_score_weight": min_score_weight,
                    "max_score_weight": max_score_weight,
                    "model": model,
                },
                "items": rows,   # per-comment breakdown
            },
        }
