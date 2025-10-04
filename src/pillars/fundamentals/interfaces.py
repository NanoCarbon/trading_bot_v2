# src/pillars/fundamentals/interfaces.py
from typing import Protocol, Dict, Any, runtime_checkable

Vote = Dict[str, Any]

@runtime_checkable
class FundamentalTool(Protocol):
    """Interface for fundamentals-based tools (e.g., P/E)."""
    name: str
    pillar: str  # should be "fundamentals"

    def compute(self, *args, **kwargs) -> Vote:
        ...
