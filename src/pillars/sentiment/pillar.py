from typing import List, Dict, Any
from .interfaces import Vote, SentimentTool
from .wsb_stub import WSBStubTool

REGISTRY: Dict[str, type[SentimentTool]] = {
    "WSB": WSBStubTool,   # Add real tools later (e.g., "WSB_VADER": WSBVaderTool)
}

class SentimentPillar:
    """
    Aggregates enabled sentiment tools. For now, it just runs whatever is listed in cfg.
    Example cfg:
      cfg["sentiment"]["enabled"] = ["WSB"]
    """
    def __init__(self, enabled: List[str]):
        self.tools: List[SentimentTool] = [REGISTRY[name]() for name in enabled if name in REGISTRY]

    def compute_all(self, ticker: str, cfg: Dict[str, Any]) -> List[Vote]:
        votes: List[Vote] = []
        for tool in self.tools:
            # for now all tools only need the ticker
            votes.append(tool.compute(ticker))
        return votes
