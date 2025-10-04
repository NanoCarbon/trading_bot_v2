# Trading Bot — Technicals • Fundamentals • Sentiment

A clean, config-driven research scaffold that:

- pulls daily OHLCV via **yfinance**
- computes **Technicals** votes (RSI, Triple SMA with slope/stack logic, Bollinger Bands, Price↑+Volume↑, and **History Similarity** on price)
- computes **Fundamentals** votes (**P/E ratio** banding)
- (optionally) computes **Sentiment** from Reddit comments with an LLM classifier and recency/upvote weighting
- stores every vote (with supporting data) in **SQLite** for later analysis, weighting, or LLM consensus

> Design goal: keep pillars **modular** and **odd in count** to reduce ties. Each tool emits a normalized vote:  
> {"pillar","tool","signal","vote","confidence","reason","data"}

---

## Project layout

```
trading_bot_v2/
  config.toml
  main.py
  requirements.txt
  .gitignore
  src/
    config.py
    collector.py
    db.py
    pillars/
      technicals/
        __init__.py
        interfaces.py
        utils.py
        rsi.py
        triple_sma.py
        bollinger.py
        price_volume.py
        hist_similarity.py     # moved from fundamentals → technicals
        pillar.py              # (optional aggregator, if you enable it later)
      fundamentals/
        __init__.py
        interfaces.py
        pe_ratio.py
        pillar.py              # (registry/aggregation if you want it)
      sentiment/
        __init__.py
        interfaces.py
        utils.py
        reddit_sentiment.py
    tools/
      reddit_client.py
  data/
    votes.sqlite               # created on first run
```

---

## Quick start

### 1) Install

- Python **3.11+** recommended

```bash
pip install -r requirements.txt
```

### 2) Configure

Edit **`config.toml`** (defaults shown):

```toml
[run]
default_ticker = "JPM"
db_path = "data/votes.sqlite"

[fetch]
lookback_days = 250

# -------------------- TECHNICALS --------------------

[rsi]
period = 14
oversold = 20.0
overbought = 80.0

[sma]
short = 20
mid = 50
long = 200
equal_is_below = true
slope_window = 10
slope_tol = 0.0

[bollinger]
window = 20
k = 2.0
equal_is_inside = true

[price_volume]
window = 5
vol_ratio_min = 1.10

[hist_sim]   # history similarity on price (now a technical)
window = 20
horizon = 5
top_k = 10

# -------------------- FUNDAMENTALS --------------------

[pe_ratio]
buy_below = 15.0
hold_upper = 25.0
allow_forward = true  # fallback to forward PE if trailing missing

# -------------------- SENTIMENT --------------------

[sentiment]
enabled = true        # set false to disable
subreddits = ["stocks", "investing", "wallstreetbets"]
synonyms = []
max_comments = 50
classify_top_n = 15
max_age_days = 7.0
half_life_days = 3.0
min_score_weight = 0.5
max_score_weight = 2.0
model = "gpt-4o-mini"
```

### 3) Optional environment

If **sentiment** is enabled, you’ll need:

- **OpenAI**: `OPENAI_API_KEY`
- **Reddit (PRAW)**: `REDDIT_CLIENT_ID`, `REDDIT_SECRET`, `REDDIT_USER_AGENT`

Create a `.env` (not committed) if you like:

```
OPENAI_API_KEY=sk-...
REDDIT_CLIENT_ID=xxxxxxxxxxxxxx
REDDIT_SECRET=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
REDDIT_USER_AGENT=windows:trading-bot:v0.1 (by u/yourname)
```

> Ensure your `.gitignore` includes `.env` and that the file was never committed.  
> If it was committed, rotate keys and rewrite history (e.g., `git filter-repo`), then push with force.

---

## Run

```bash
python main.py
# override ticker:
python main.py --ticker SPY
# use a different config path:
python main.py --config my_config.toml
```

You’ll see pillar/tool outputs in the console. All votes are persisted to SQLite at `data/votes.sqlite`.

---

## What gets computed

### Pillar: Technicals

Every indicator returns:

```json
{
  "pillar": "technicals",
  "tool": "RSI | TRIPLE_SMA | BOLLINGER | PRICE_VOLUME | HIST_SIM",
  "signal": "BUY | SELL | HOLD",
  "vote": 1 | 0 | -1,
  "confidence": 0.0..1.0,
  "reason": "human readable",
  "data": { "...supporting numbers..." }
}
```

- **RSI (Wilder)** — BUY when ≤ oversold; SELL when ≥ overbought; else HOLD.  
- **Triple SMA (20/50/200)** — reports stack, slopes, price above/below, tail values; simple playbook:
  - Bullish: S₁>S₂>S₃ and slopes ≥ 0 ⇒ BUY
  - Bearish: S₁<S₂<S₃ and slopes ≤ 0 ⇒ SELL
  - Otherwise ⇒ HOLD
- **Bollinger Bands (20, 2σ)** — BUY if price below lower band; SELL if above upper band; else HOLD.  
- **Price↑ + Volume↑** — last *N* vs prior *N*: Price↑ with Volume↑ ⇒ BUY; Price↓ with Volume↑ ⇒ SELL; else HOLD.  
- **History Similarity (price)** — finds top-*k* past windows most similar (z-norm corr) to recent window; uses average forward-*horizon* return to vote.

### Pillar: Fundamentals

- **P/E Ratio (TTM; optional forward fallback)** — simple bands:
  - P/E < `buy_below` ⇒ **BUY**
  - `buy_below`…`hold_upper` ⇒ **HOLD**
  - P/E > `hold_upper` ⇒ **SELL**
  - Confidence increases as P/E sits farther from thresholds.

### Pillar: Sentiment (Reddit, optional)

- Fetches recent comments from configured subreddits that mention your ticker (`$TICKER` or whole word).  
- Batches comments to an **OpenAI** model (default `gpt-4o-mini`) for **Bullish/Bearish/Neutral** classification with optional model confidence.  
- Aggregates with **recency decay** (half-life) + gentle **upvote weight**.  
- Emits **BUY/SELL/HOLD** + confidence; also logs raw classified items to a `sentiment` table when DB/run id are provided.

**Make sentiment optional**:

- In `config.toml`: set `sentiment.enabled = false`  
  **or**
- Env override at runtime: `SKIP_SENTIMENT=1 python main.py`

When disabled (or on errors/rate-limits), a neutral **HOLD** vote is recorded with a reason.

---

## Storage (SQLite)

Created automatically (see `src/db.py`).

Tables:
- `runs(id, created_at, ticker, asof, price_close)`
- `votes(id, run_id, pillar, tool, vote, confidence, signal, reason, payload)`
- `sentiment(id, run_id, ticker, comment_id, subreddit, author, body, score, created_utc, sentiment, sentiment_score, confidence_model, weight, permalink)`

Peek at recent votes:

```bash
sqlite3 data/votes.sqlite "SELECT pillar, tool, vote, signal, substr(reason,1,60), substr(payload,1,100) FROM votes ORDER BY id DESC LIMIT 10;"
```

---

## Notes & caveats

- **Reddit API**: Respect rate limits. If you see 401s, verify `REDDIT_CLIENT_ID/SECRET/USER_AGENT`, and ensure your app is configured as *script* on https://www.reddit.com/prefs/apps/
- **OpenAI**: Set `OPENAI_API_KEY`. You can swap models via `config.toml`.
- **yfinance**: Some fundamentals fields can be missing; the P/E tool tries multiple sources and falls back to forward P/E (configurable).

---

## Roadmap

- Pillar-level combiner (e.g., per-pillar consensus → overall vote)
- Expand Fundamentals: EV/EBITDA, growth, margins, leverage, macro regime overlay
- Batch backtesting & confidence learning (feedback loop)
- Streamlit dashboard for runs, drill-downs, and “what-if” re-weighting
- Vector store for evidence and LLM rationale augmentation

---

## License

MIT (see `LICENSE` if provided). Use at your own risk — **not investment advice**.
