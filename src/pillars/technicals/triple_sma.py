# src/pillars/technicals/triple_sma.py
from __future__ import annotations

import numpy as np
import pandas as pd
from dataclasses import dataclass
from typing import Tuple, Dict, Any

from .interfaces import TechnicalIndicator, Vote
from .utils import _ensure_1d_series


def _sma(s: pd.Series, window: int) -> pd.Series:
    return s.rolling(window=window, min_periods=window).mean()


def _slope(series: pd.Series, last_n: int = 10) -> float:
    """
    Return the linear-regression slope of the last N points.
    Units: price per index-step (rough, but monotonic for sign checks).
    """
    s = series.dropna()
    if len(s) < max(3, last_n):
        return 0.0
    y = s.iloc[-last_n:].to_numpy(dtype=float)
    x = np.arange(len(y), dtype=float)
    m, _b = np.polyfit(x, y, 1)
    return float(m)


def _tail_list(series: pd.Series, n: int = 5):
    s = series.dropna().tail(n)
    out = []
    for idx, val in s.items():
        d = idx.isoformat() if hasattr(idx, "isoformat") else str(idx)
        out.append({"date": d, "value": float(val)})
    return out


@dataclass
class TripleSMAConfig:
    windows: Tuple[int, int, int] = (20, 50, 200)  # (fast, mid, slow)
    equal_is_below: bool = True
    slope_window: int = 10   # lookback for slope calc
    slope_tol: float = 0.0   # require >= tol for bullish, <= -tol for bearish


class TripleSMAIndicator(TechnicalIndicator):
    """
    Triple SMA with simple playbook:

      Let S1=fast (e.g., 20), S2=mid (50), S3=slow (200).

      Bullish structure:
        S1 > S2 > S3  AND  slopes(S1,S2,S3) >= 0 (within `slope_tol`)
        → BUY

      Bearish structure:
        S1 < S2 < S3  AND  slopes(S1,S2,S3) <= 0 (within `slope_tol`)
        → SELL

      Else:
        Mixed stacks or conflicting/flat slopes
        → HOLD  (“repair/deterioration/range”)
    """

    name = "TRIPLE_SMA"
    pillar = "technicals"

    def compute(
        self,
        close,
        *,
        windows: Tuple[int, int, int] = TripleSMAConfig.windows,
        equal_is_below: bool = TripleSMAConfig.equal_is_below,
        slope_window: int = TripleSMAConfig.slope_window,
        slope_tol: float = TripleSMAConfig.slope_tol,
    ) -> Vote:
        s_close = _ensure_1d_series(close)
        if s_close.empty:
            return {
                "pillar": self.pillar, "tool": self.name,
                "signal": "HOLD", "vote": 0, "confidence": 0.5,
                "reason": "no price data",
                "data": {}
            }

        w1, w2, w3 = windows
        ma1 = _sma(s_close, w1)
        ma2 = _sma(s_close, w2)
        ma3 = _sma(s_close, w3)

        # latest values
        price = float(s_close.iloc[-1])
        v1 = float(ma1.dropna().iloc[-1]) if not ma1.dropna().empty else None
        v2 = float(ma2.dropna().iloc[-1]) if not ma2.dropna().empty else None
        v3 = float(ma3.dropna().iloc[-1]) if not ma3.dropna().empty else None

        # above/below map
        def _rel(p: float | None, m: float | None) -> str:
            if p is None or m is None:
                return "n/a"
            if p > m:
                return "above"
            elif p == m:
                return "below" if equal_is_below else "above"
            else:
                return "below"

        above_below = {
            w1: _rel(price, v1),
            w2: _rel(price, v2),
            w3: _rel(price, v3),
        }

        # slopes
        s1 = _slope(ma1, last_n=slope_window)
        s2 = _slope(ma2, last_n=slope_window)
        s3 = _slope(ma3, last_n=slope_window)

        have_vals = (v1 is not None) and (v2 is not None) and (v3 is not None)

        # stack conditions
        bullish_stack = have_vals and (v1 > v2 > v3)
        bearish_stack = have_vals and (v1 < v2 < v3)

        # slope conditions (tolerant around zero if slope_tol>0)
        bullish_slopes = (s1 >= slope_tol) and (s2 >= slope_tol) and (s3 >= slope_tol)
        bearish_slopes = (s1 <= -slope_tol) and (s2 <= -slope_tol) and (s3 <= -slope_tol)

        # decide
        if bullish_stack and bullish_slopes:
            signal, vote, conf = "BUY", 1, 0.6
            reason = "Bullish stack S1>S2>S3 with non-negative slopes → persistent uptrend; favor longs."
        elif bearish_stack and bearish_slopes:
            signal, vote, conf = "SELL", -1, 0.6
            reason = "Bearish stack S1<S2<S3 with non-positive slopes → persistent downtrend; avoid longs."
        else:
            signal, vote, conf = "HOLD", 0, 0.5
            reason = (
                "Mixed stack or conflicting slopes → transition/range; defer to other evidence."
            )

        # payload (JSON-safe)
        data: Dict[str, Any] = {
            "price": price,
            "windows": windows,
            "values": {w1: v1, w2: v2, w3: v3},
            "above_below": above_below,
            "slopes": {w1: s1, w2: s2, w3: s3, "window": slope_window, "tol": slope_tol},
            "tails": {
                w1: _tail_list(ma1),
                w2: _tail_list(ma2),
                w3: _tail_list(ma3),
            },
            "playbook": {
                "bullish": "S1 > S2 > S3 and slopes >= 0 → BUY",
                "bearish": "S1 < S2 < S3 and slopes <= 0 → SELL",
                "else": "HOLD",
            },
        }

        return {
            "pillar": self.pillar,
            "tool": self.name,
            "signal": signal,
            "vote": vote,
            "confidence": conf,
            "reason": reason,
            "data": data,
        }
