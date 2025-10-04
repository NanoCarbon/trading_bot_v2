# src/pillars/technicals/rsi.py
from __future__ import annotations

import numpy as np
import pandas as pd

from .interfaces import TechnicalIndicator, Vote
from .utils import _ensure_1d_series


def _rsi_from_close(close: pd.Series, period: int = 14) -> pd.Series:
    s = _ensure_1d_series(close)
    if s.empty:
        return pd.Series(dtype=float)
    delta = s.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1/period, adjust=False, min_periods=period).mean()
    avg_loss = loss.ewm(alpha=1/period, adjust=False, min_periods=period).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


class RSIIndicator(TechnicalIndicator):
    name = "RSI"
    pillar = "technicals"

    def compute(
        self,
        close,
        *,
        period: int = 14,
        oversold: float = 20.0,
        overbought: float = 80.0,
    ) -> Vote:
        rsi_series = _rsi_from_close(close, period).dropna()
        if rsi_series.empty:
            return {
                "pillar": self.pillar, "tool": self.name,
                "signal": "HOLD", "vote": 0, "confidence": 0.5,
                "reason": "insufficient data",
                "data": {}
            }
        val = float(rsi_series.iloc[-1])
        if val <= oversold:
            signal, vote, conf = "BUY", 1, 0.6
            reason = f"RSI {val:.1f} ≤ {oversold}"
        elif val >= overbought:
            signal, vote, conf = "SELL", -1, 0.6
            reason = f"RSI {val:.1f} ≥ {overbought}"
        else:
            signal, vote, conf = "HOLD", 0, 0.5
            reason = f"RSI {val:.1f} between {oversold} and {overbought}"

        return {
            "pillar": self.pillar,
            "tool": self.name,
            "signal": signal,
            "vote": vote,
            "confidence": conf,
            "reason": reason,
            "data": {"last": val, "period": period, "oversold": oversold, "overbought": overbought},
        }
