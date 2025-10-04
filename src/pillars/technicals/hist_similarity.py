# src/pillars/technicals/hist_similarity.py
from __future__ import annotations

import numpy as np
import pandas as pd

from .interfaces import TechnicalIndicator, Vote
from .utils import _ensure_1d_series


class HistorySimilarityIndicator(TechnicalIndicator):
    """
    Match the most recent W-day window against all historical W-day windows
    (z-normalized), take top-K most correlated, and average their forward
    horizon returns to make a directional vote.
    """
    name = "HIST_SIM"
    pillar = "technicals"

    def compute(
        self,
        close,
        *,
        window: int = 20,
        horizon: int = 5,
        top_k: int = 10,
    ) -> Vote:
        s = _ensure_1d_series(close)
        if len(s) < window + horizon + 5:
            return {
                "pillar": self.pillar, "tool": self.name,
                "signal": "HOLD", "vote": 0, "confidence": 0.5,
                "reason": "insufficient history",
                "data": {}
            }

        recent = s.iloc[-window:].values
        r_mu, r_sd = recent.mean(), recent.std() or 1.0
        rz = (recent - r_mu) / r_sd

        scores = []
        for i in range(0, len(s) - window - horizon):
            hist = s.iloc[i:i + window].values
            h_mu, h_sd = hist.mean(), hist.std() or 1.0
            hz = (hist - h_mu) / h_sd
            corr = float(np.corrcoef(rz, hz)[0, 1])
            fwd_ret = float(s.iloc[i + window + horizon - 1] / s.iloc[i + window - 1] - 1.0)
            scores.append((s.index[i + window - 1], corr, fwd_ret))

        if not scores:
            return {
                "pillar": self.pillar, "tool": self.name,
                "signal": "HOLD", "vote": 0, "confidence": 0.5,
                "reason": "no comparable windows",
                "data": {}
            }

        scores.sort(key=lambda x: x[1], reverse=True)
        top = scores[:top_k]
        mean_ret = float(np.mean([x[2] for x in top]))

        if mean_ret > 0:
            signal, vote, conf = "BUY", 1, 0.55
        elif mean_ret < 0:
            signal, vote, conf = "SELL", -1, 0.55
        else:
            signal, vote, conf = "HOLD", 0, 0.5

        payload = {
            "window": window,
            "horizon": horizon,
            "top_k": top_k,
            "mean_forward_return": mean_ret,
            "top_matches": [{"asof": str(t), "corr": c, "fwd_return": r} for (t, c, r) in top],
        }
        return {
            "pillar": self.pillar, "tool": self.name,
            "signal": signal, "vote": vote, "confidence": conf,
            "reason": f"Avg fwd {horizon}d return among top-{top_k} matches = {mean_ret:.2%}",
            "data": payload
        }
