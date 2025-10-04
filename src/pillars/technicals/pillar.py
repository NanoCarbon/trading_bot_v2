# src/pillars/technicals/pillar.py
from __future__ import annotations

from typing import List, Dict

from .interfaces import TechnicalIndicator, Vote
from .rsi import RSIIndicator
from .triple_sma import TripleSMAIndicator
from .bollinger import BollingerIndicator
from .price_volume import PriceVolumeIndicator
from .hist_similarity import HistorySimilarityIndicator


REGISTRY: Dict[str, type[TechnicalIndicator]] = {
    "RSI": RSIIndicator,
    "TRIPLE_SMA": TripleSMAIndicator,
    "BOLLINGER": BollingerIndicator,
    "PRICE_VOLUME": PriceVolumeIndicator,
    "HIST_SIM": HistorySimilarityIndicator,
}


class PillarTechnicals:
    """Optional aggregator if you want to run a subset of indicators together."""
    def __init__(self, enabled: List[str] | None = None):
        enabled = enabled or list(REGISTRY.keys())
        self.indicators: List[TechnicalIndicator] = [REGISTRY[name]() for name in enabled if name in REGISTRY]

    def compute_all(self, close, **kwargs) -> List[Vote]:
        votes: List[Vote] = []
        for ind in self.indicators:
            try:
                votes.append(ind.compute(close, **(kwargs.get(ind.name, {}))))
            except Exception as e:
                votes.append({
                    "pillar": "technicals",
                    "tool": getattr(ind, "name", "UNKNOWN"),
                    "signal": "HOLD",
                    "vote": 0,
                    "confidence": 0.5,
                    "reason": f"indicator error: {e}",
                    "data": {},
                })
        return votes
