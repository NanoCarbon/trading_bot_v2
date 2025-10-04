# src/pillars/fundamentals/pe_ratio.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Dict, Any

import math
import yfinance as yf

from .interfaces import FundamentalTool, Vote


@dataclass
class PERatioConfig:
    """Simple thresholds for P/E interpretation."""
    buy_below: float = 15.0   # P/E < buy_below → BUY
    hold_upper: float = 25.0  # P/E > hold_upper → SELL (else HOLD)
    allow_forward: bool = True  # fall back to forward P/E when trailing is missing


class PERatioTool(FundamentalTool):
    """
    Fetches a ticker's P/E (TTM if available; optionally falls back to forward P/E)
    and emits a BUY/SELL/HOLD vote using configurable thresholds.

    Rules (default):
      P/E < 15  → BUY
      15–25     → HOLD
      > 25      → SELL
    """

    name = "PE_RATIO"
    pillar = "fundamentals"

    def _get_pe(self, ticker: str, allow_forward: bool) -> tuple[Optional[float], str]:
        """
        Try multiple sources in yfinance:
          1) fast_info.trailing_pe
          2) get_info()["trailingPE"]
          3) (optional) fast_info.forward_pe
          4) (optional) get_info()["forwardPE"]
        Returns (pe_value, source_label).
        """
        tk = yf.Ticker(ticker)

        # 1) fast_info.trailing_pe
        try:
            pe = getattr(tk.fast_info, "trailing_pe", None)
            if pe is not None and isinstance(pe, (int, float)) and pe > 0 and math.isfinite(pe):
                return float(pe), "fast_info.trailing_pe"
        except Exception:
            pass

        # 2) get_info()["trailingPE"]
        try:
            info = tk.get_info()
            pe = info.get("trailingPE")
            if pe is not None and isinstance(pe, (int, float)) and pe > 0 and math.isfinite(pe):
                return float(pe), "info.trailingPE"
        except Exception:
            pass

        if allow_forward:
            # 3) fast_info.forward_pe
            try:
                pe = getattr(tk.fast_info, "forward_pe", None)
                if pe is not None and isinstance(pe, (int, float)) and pe > 0 and math.isfinite(pe):
                    return float(pe), "fast_info.forward_pe"
            except Exception:
                pass

            # 4) get_info()["forwardPE"]
            try:
                if "info" not in locals():
                    info = tk.get_info()
                pe = info.get("forwardPE")
                if pe is not None and isinstance(pe, (int, float)) and pe > 0 and math.isfinite(pe):
                    return float(pe), "info.forwardPE"
            except Exception:
                pass

        return None, "unavailable"

    def compute(
        self,
        ticker: str,
        *,
        buy_below: float = PERatioConfig.buy_below,
        hold_upper: float = PERatioConfig.hold_upper,
        allow_forward: bool = PERatioConfig.allow_forward,
    ) -> Vote:
        pe, source = self._get_pe(ticker, allow_forward=allow_forward)

        if pe is None:
            return {
                "pillar": self.pillar,
                "tool": self.name,
                "signal": "HOLD",
                "vote": 0,
                "confidence": 0.5,
                "reason": "P/E unavailable from yfinance",
                "data": {
                    "ticker": ticker,
                    "pe": None,
                    "source": source,
                    "thresholds": {"buy_below": buy_below, "hold_upper": hold_upper},
                },
            }

        # Decision
        if pe < buy_below:
            signal, vote = "BUY", 1
        elif pe > hold_upper:
            signal, vote = "SELL", -1
        else:
            signal, vote = "HOLD", 0

        # Confidence: a light bump when farther from boundaries
        # normalize distance to nearest boundary
        nearest = min(abs(pe - buy_below), abs(pe - hold_upper))
        # scale into [0, 0.4] then add base 0.5; cap at 0.9
        conf = min(0.9, 0.5 + min(0.4, nearest / max(1.0, (hold_upper - buy_below) / 2.0) * 0.4))

        return {
            "pillar": self.pillar,
            "tool": self.name,
            "signal": signal,
            "vote": vote,
            "confidence": conf if vote != 0 else 0.5,
            "reason": f"P/E={pe:.2f} via {source}; thresholds: <{buy_below} BUY, {buy_below}–{hold_upper} HOLD, >{hold_upper} SELL",
            "data": {
                "ticker": ticker,
                "pe": pe,
                "source": source,
                "thresholds": {"buy_below": buy_below, "hold_upper": hold_upper},
            },
        }
