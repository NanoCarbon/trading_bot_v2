# src/collector.py
from __future__ import annotations

import os
import pandas as pd
import yfinance as yf
from .db import init_db, insert_run, insert_vote

# class-based technicals
from .pillars.technicals import (
    RSIIndicator,
    TripleSMAIndicator,
    BollingerIndicator,
    PriceVolumeIndicator,
    HistorySimilarityIndicator,
)
from .pillars.technicals.utils import _ensure_1d_series

# fundamentals (explicit submodule import)
from .pillars.fundamentals.pe_ratio import PERatioTool

# sentiment
from .pillars.sentiment import RedditBatchSentimentTool


def fetch_prices(ticker: str, lookback_days: int) -> pd.DataFrame:
    df = yf.download(
        ticker,
        period=f"{lookback_days}d",
        interval="1d",
        auto_adjust=True,
        progress=False,
        threads=False,
    )
    df = df.rename(columns=str.lower)
    df.index.name = "date"
    return df


def run_once(ticker: str, cfg: dict):
    df = fetch_prices(ticker, cfg["fetch"]["lookback_days"])
    if df.empty:
        raise RuntimeError(f"No price data for {ticker}")

    close = _ensure_1d_series(df.get("close"))
    volume = _ensure_1d_series(df.get("volume")).reindex(close.index)

    asof = close.index[-1].strftime("%Y-%m-%d")
    last_close = float(close.iloc[-1])

    # --- persist run first ---
    con = init_db(cfg["run"]["db_path"])
    run_id = insert_run(con, ticker, asof, last_close)

    # --- technicals ---
    rsi_vote = RSIIndicator().compute(close, **cfg["rsi"])
    sma_vote = TripleSMAIndicator().compute(
        close,
        windows=(cfg["sma"]["short"], cfg["sma"]["mid"], cfg["sma"]["long"]),
        equal_is_below=cfg["sma"]["equal_is_below"],
    )
    boll_vote = BollingerIndicator().compute(close, **cfg["bollinger"])
    pv_vote   = PriceVolumeIndicator().compute(close, volume, **cfg["price_volume"])
    hist_sim_vote = HistorySimilarityIndicator().compute(close, **cfg["hist_sim"])
    tech_votes = [rsi_vote, sma_vote, boll_vote, pv_vote, hist_sim_vote]

    # --- fundamentals (PE ratio) ---
    try:
        pe_vote = PERatioTool().compute(ticker, **cfg.get("pe_ratio", {}))
    except Exception as e:
        pe_vote = {
            "pillar": "fundamentals", "tool": "PE_RATIO",
            "signal": "HOLD", "vote": 0, "confidence": 0.5,
            "reason": f"PE lookup failed: {type(e).__name__}",
            "data": {"error": str(e)[:200]},
        }

    # --- sentiment (optional) ---
    sentiment_enabled_cfg = cfg.get("sentiment", {}).get("enabled", True)
    sentiment_enabled_env = os.getenv("SKIP_SENTIMENT", "0") != "1"
    sentiment_enabled = sentiment_enabled_cfg and sentiment_enabled_env

    if sentiment_enabled:
        try:
            sent_vote = RedditBatchSentimentTool().compute(
                ticker,
                subreddits=cfg["sentiment"]["subreddits"],
                synonyms=cfg["sentiment"].get("synonyms", []),
                max_comments=cfg["sentiment"].get("max_comments", 50),
                classify_top_n=cfg["sentiment"].get("classify_top_n", 15),
                half_life_days=cfg["sentiment"].get("half_life_days", 3.0),
                min_score_weight=cfg["sentiment"].get("min_score_weight", 0.5),
                max_score_weight=cfg["sentiment"].get("max_score_weight", 2.0),
                model=cfg["sentiment"].get("model", "gpt-4o-mini"),
                max_age_days=cfg["sentiment"].get("max_age_days", 7.0),
                db_con=con,
                run_id=run_id,
            )
        except Exception as e:
            sent_vote = {
                "pillar": "sentiment", "tool": "REDDIT_SENTIMENT",
                "signal": "HOLD", "vote": 0, "confidence": 0.5,
                "reason": f"sentiment skipped due to error: {type(e).__name__}",
                "data": {"error": str(e)[:200]},
            }
    else:
        sent_vote = {
            "pillar": "sentiment", "tool": "REDDIT_SENTIMENT",
            "signal": "HOLD", "vote": 0, "confidence": 0.5,
            "reason": "sentiment disabled via config/env",
            "data": {},
        }

    # include fundamentals + sentiment
    votes = tech_votes + [pe_vote, sent_vote]

    # --- store votes ---
    for v in votes:
        insert_vote(con, run_id, v["pillar"], v["tool"], v["vote"], v.get("confidence"),
                    v["signal"], v.get("reason", ""), v.get("data", {}))

    return run_id, votes, {"ticker": ticker, "asof": asof, "close": last_close}
