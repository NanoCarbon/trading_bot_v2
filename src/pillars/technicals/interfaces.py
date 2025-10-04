# src/pillars/technicals/interfaces.py
from typing import Protocol, Dict, Any, runtime_checkable

# Consistent shape we return from all tools
Vote = Dict[str, Any]

@runtime_checkable
class TechnicalIndicator(Protocol):
    """Interface for all technical indicator tools under 'technicals'."""
    name: str          # e.g., "RSI", "TRIPLE_SMA"
    pillar: str        # should be "technicals"

    def compute(self, close, *args, **kwargs) -> Vote:
        """Return a Vote dict with keys:
           pillar, tool, signal, vote, confidence, reason, data
        """
        ...
