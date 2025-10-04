# src/pillars/technicals/price_volume.py
from __future__ import annotations

import pandas as pd

from .interfaces import TechnicalIndicator, Vote
from .utils import _ensure_1d_series


class PriceVolumeIndicator(TechnicalIndicator):
    """
    Simple rising-price-with-rising-volume (and the inverse) detector.
    Compares last N days vs the previous N days.
    """
    name = "PRICE_VOLUME"
    pillar = "technicals"

    def compute(
        self,
        close,
        volume=None,
        *,
        window: int = 5,
        vol_ratio_min: float = 1.10,
    ) -> Vote:
        c = _ensure_1d_series(close)
        v = _ensure_1d_series(volume).reindex(c.index)

        v = v.ffill().fillna(0.0)

        if len(c) < window * 2:
            return {
                "pillar": self.pillar, "tool": self.name,
                "signal": "HOLD", "vote": 0, "confidence": 0.5,
                "reason": "insufficient data", "data": {}
            }

        recent_c = c.tail(window)
        prior_c = c.shift(window).tail(window)

        recent_v = float(v.tail(window).mean())
        prior_v = float(v.shift(window).tail(window).mean())

        price_change = float(recent_c.iloc[-1] / prior_c.iloc[-1] - 1.0) if prior_c.iloc[-1] != 0 else 0.0
        vol_ratio = float(recent_v / prior_v) if prior_v != 0 else 0.0

        rising_vol = vol_ratio >= vol_ratio_min
        rising_price = price_change > 0
        falling_price = price_change < 0

        if rising_price and rising_vol:
            signal, vote, conf = "BUY", 1, 0.55
            reason = f"Price↑ {price_change:.2%} with Volume↑ {vol_ratio:.2f}x"
        elif falling_price and rising_vol:
            signal, vote, conf = "SELL", -1, 0.55
            reason = f"Price↓ {price_change:.2%} with Volume↑ {vol_ratio:.2f}x"
        else:
            signal, vote, conf = "HOLD", 0, 0.5
            reason = f"PriceΔ {price_change:.2%}, Vol× {vol_ratio:.2f}"

        return {
            "pillar": self.pillar, "tool": self.name,
            "signal": signal, "vote": vote, "confidence": conf,
            "reason": reason,
            "data": {"window": window, "price_change": price_change, "vol_ratio": vol_ratio}
        }
