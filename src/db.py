# src/db.py
from __future__ import annotations

import os
import json
import sqlite3
import numpy as np

try:
    import pandas as pd
except Exception:  # pandas is optional
    pd = None


SCHEMA = """
-- Runs: one per execution of the pipeline
CREATE TABLE IF NOT EXISTS runs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  ticker TEXT NOT NULL,
  asof TEXT NOT NULL,
  price_close REAL
);

-- Votes: one row per tool output in a run
CREATE TABLE IF NOT EXISTS votes (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  run_id INTEGER NOT NULL,
  pillar TEXT NOT NULL,
  tool TEXT NOT NULL,
  vote INTEGER NOT NULL,
  confidence REAL,
  signal TEXT,
  reason TEXT,
  payload TEXT,
  FOREIGN KEY (run_id) REFERENCES runs(id)
);

-- Reddit per-comment sentiment logging (optional)
CREATE TABLE IF NOT EXISTS sentiment_comments (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  run_id INTEGER NOT NULL,
  ticker TEXT NOT NULL,
  comment_id TEXT NOT NULL,
  subreddit TEXT,
  author TEXT,
  body TEXT,
  score INTEGER,
  created_utc REAL,
  sentiment TEXT,            -- "Bullish" | "Bearish" | "Neutral"
  sentiment_score INTEGER,   -- +1 / 0 / -1
  confidence_model REAL,     -- LLM-reported confidence (0..1)
  weight REAL,               -- our aggregated weight (age * score factor)
  permalink TEXT,
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  FOREIGN KEY (run_id) REFERENCES runs(id)
);

CREATE INDEX IF NOT EXISTS idx_votes_run ON votes(run_id);
CREATE INDEX IF NOT EXISTS idx_sent_run ON sentiment_comments(run_id);
CREATE INDEX IF NOT EXISTS idx_sent_ticker ON sentiment_comments(ticker);
CREATE UNIQUE INDEX IF NOT EXISTS idx_sent_unique ON sentiment_comments(run_id, comment_id);
"""


def init_db(path: str) -> sqlite3.Connection:
    """Create the SQLite file and ensure schema exists."""
    dname = os.path.dirname(path)
    if dname:
        os.makedirs(dname, exist_ok=True)
    con = sqlite3.connect(path)
    con.executescript(SCHEMA)
    return con


def _json_safe(obj):
    """Convert numpy/pandas/sets/etc. to JSON-serializable primitives."""
    # dict: ensure string keys and recurse
    if isinstance(obj, dict):
        return {str(k): _json_safe(v) for k, v in obj.items()}

    # lists/tuples/sets
    if isinstance(obj, (list, tuple, set)):
        return [_json_safe(x) for x in obj]

    # numpy scalars
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating,)):
        return float(obj)
    if isinstance(obj, (np.bool_,)):
        return bool(obj)

    # pandas Timestamp
    if pd is not None and isinstance(obj, getattr(pd, "Timestamp", ())):
        return obj.isoformat()

    # numpy arrays
    if hasattr(obj, "tolist"):
        try:
            return obj.tolist()
        except Exception:
            pass

    return obj


def insert_run(con: sqlite3.Connection, ticker: str, asof: str, price_close: float | None) -> int:
    cur = con.execute(
        "INSERT INTO runs (ticker, asof, price_close) VALUES (?, ?, ?)",
        (ticker, asof, None if price_close is None else float(price_close)),
    )
    con.commit()
    return int(cur.lastrowid)


def insert_vote(
    con: sqlite3.Connection,
    run_id: int,
    pillar: str,
    tool: str,
    vote: int,
    confidence: float | None,
    signal: str,
    reason: str,
    payload: dict | None,
) -> None:
    safe_payload = _json_safe(payload or {})
    con.execute(
        "INSERT INTO votes (run_id, pillar, tool, vote, confidence, signal, reason, payload) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (
            int(run_id),
            pillar,
            tool,
            int(vote),
            None if confidence is None else float(confidence),
            signal,
            reason,
            json.dumps(safe_payload, ensure_ascii=False),
        ),
    )
    con.commit()


def insert_sentiment_rows(
    con: sqlite3.Connection,
    run_id: int,
    ticker: str,
    rows: list[dict],
) -> None:
    """
    Bulk insert per-comment Reddit sentiment rows.
    Each row dict should contain:
      comment_id, subreddit, author, body, score, created_utc,
      sentiment, sentiment_score, confidence_model, weight, permalink
    """
    if not rows:
        return

    # Normalize types and guard missing keys
    normalized = []
    for r in rows:
        normalized.append(
            (
                int(run_id),
                str(ticker),
                str(r.get("comment_id", "")),
                r.get("subreddit"),
                r.get("author"),
                r.get("body"),
                None if r.get("score") is None else int(r.get("score", 0)),
                None if r.get("created_utc") is None else float(r.get("created_utc", 0.0)),
                r.get("sentiment"),
                None if r.get("sentiment_score") is None else int(r.get("sentiment_score", 0)),
                None if r.get("confidence_model") is None else float(r.get("confidence_model", 0.0)),
                None if r.get("weight") is None else float(r.get("weight", 0.0)),
                r.get("permalink"),
            )
        )

    con.executemany(
        """
        INSERT OR IGNORE INTO sentiment_comments (
          run_id, ticker, comment_id, subreddit, author, body, score, created_utc,
          sentiment, sentiment_score, confidence_model, weight, permalink
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        normalized,
    )
    con.commit()
