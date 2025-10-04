# src/pillars/technicals/bollinger.py
from __future__ import annotations

from .interfaces import TechnicalIndicator, Vote
from .utils import _ensure_1d_series


class BollingerIndicator(TechnicalIndicator):
    name = "BOLLINGER"
    pillar = "technicals"

    def compute(
        self,
        close,
        *,
        window: int = 20,
        k: float = 2.0,
        equal_is_inside: bool = True,
    ) -> Vote:
        s = _ensure_1d_series(close)
        if len(s) < window:
            return {
                "pillar": self.pillar, "tool": self.name,
                "signal": "HOLD", "vote": 0, "confidence": 0.5,
                "reason": "insufficient data", "data": {}
            }

        ma = s.rolling(window, min_periods=window).mean()
        sd = s.rolling(window, min_periods=window).std()
        upper = ma + k * sd
        lower = ma - k * sd

        price = float(s.iloc[-1])
        u, l = float(upper.iloc[-1]), float(lower.iloc[-1])

        # decision
        if equal_is_inside:
            if price > u:
                signal, vote, outside = "SELL", -1, (price - u)
            elif price < l:
                signal, vote, outside = "BUY", 1, (l - price)
            else:
                signal, vote, outside = "HOLD", 0, 0.0
        else:
            if price >= u:
                signal, vote, outside = "SELL", -1, max(0.0, price - u)
            elif price <= l:
                signal, vote, outside = "BUY", 1, max(0.0, l - price)
            else:
                signal, vote, outside = "HOLD", 0, 0.0

        bandwidth = max(1e-9, u - l)
        outside_frac = float(max(0.0, outside) / bandwidth)
        outside_frac = min(2.0, outside_frac)
        conf = 0.5 if vote == 0 else float(min(0.9, 0.5 + 0.4 * outside_frac))

        reason = (
            f"Price {price:.2f} inside bands [{l:.2f}, {u:.2f}]"
            if vote == 0 else
            (f"Price {price:.2f} > upper {u:.2f}" if vote < 0 else f"Price {price:.2f} < lower {l:.2f}")
        )

        return {
            "pillar": self.pillar, "tool": self.name,
            "signal": signal, "vote": vote, "confidence": conf, "reason": reason,
            "data": {
                "price": price, "ma": float(ma.iloc[-1]), "upper": u, "lower": l,
                "window": window, "k": k, "outside_frac": outside_frac
            }
        }
