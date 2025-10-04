from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

# Python 3.11+ has tomllib in stdlib; fall back to tomli if needed
try:  # py311+
    import tomllib as _toml
except Exception:  # older environments
    try:
        import tomli as _toml  # type: ignore
    except Exception:
        _toml = None  # no TOML reader available


DEFAULTS: Dict[str, Any] = {
    "run": {
        "default_ticker": "JPM",
        "db_path": "data/votes.sqlite",
    },
    "fetch": {
        "lookback_days": 250,
    },
    # --- Technicals ---
    "rsi": {
        "period": 14,
        "oversold": 20.0,
        "overbought": 80.0,
    },
    "sma": {
        "short": 20,
        "mid": 50,
        "long": 200,
        "equal_is_below": True,
        "slope_window": 10,
        "slope_tol": 0.0,
    },
    "bollinger": {
        "window": 20,
        "k": 2.0,
        "equal_is_inside": True,
    },
    "price_volume": {
        "window": 5,
        "vol_ratio_min": 1.10,
    },
    # Technicals: historical similarity-on-price
    "hist_sim": {
        "window": 20,
        "horizon": 5,
        "top_k": 10,
    },
    # --- Fundamentals ---
    "pe_ratio": {
        "buy_below": 15.0,
        "hold_upper": 25.0,
        "allow_forward": True,
    },
    # --- Sentiment ---
    "sentiment": {
        "subreddits": ["stocks", "investing", "wallstreetbets"],
        "synonyms": [],
        "max_comments": 50,
        "classify_top_n": 15,
        "half_life_days": 3.0,
        "min_score_weight": 0.5,
        "max_score_weight": 2.0,
        "model": "gpt-4o-mini",
        "max_age_days": 7.0,
    },
}


def _deep_update(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    """Recursively update dict `base` with `override` (mutates and returns base)."""
    for k, v in (override or {}).items():
        if (
            k in base
            and isinstance(base[k], dict)
            and isinstance(v, dict)
        ):
            _deep_update(base[k], v)
        else:
            base[k] = v
    return base


def _read_toml(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    if _toml is None:
        raise RuntimeError(
            f"Config file '{path}' found but no TOML parser is available. "
            "Install 'tomli' for Python <3.11 (e.g., pip install tomli)."
        )
    with path.open("rb") as f:
        return _toml.load(f)


def load_config(path: str | Path = "config.toml") -> Dict[str, Any]:
    """
    Load config from TOML and deep-merge with DEFAULTS.
    Returns a plain dict ready for use by the app.
    """
    cfg = {k: (v.copy() if isinstance(v, dict) else v) for k, v in DEFAULTS.items()}
    user_cfg = _read_toml(Path(path))
    _deep_update(cfg, user_cfg)

    # Basic normalizations / guards
    # Ensure lists exist for sentiment keys that expect lists
    sent = cfg.setdefault("sentiment", {})
    sent.setdefault("subreddits", DEFAULTS["sentiment"]["subreddits"])
    sent.setdefault("synonyms", DEFAULTS["sentiment"]["synonyms"])

    return cfg