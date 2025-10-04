# src/pillars/sentiment/interfaces.py
from typing import Protocol, Dict, Any, runtime_checkable

Vote = Dict[str, Any]

@runtime_checkable
class SentimentTool(Protocol):
    """Interface for sentiment tools (e.g., Reddit)."""
    name: str
    pillar: str  # should be "sentiment"

    def compute(self, *args, **kwargs) -> Vote:
        ...
