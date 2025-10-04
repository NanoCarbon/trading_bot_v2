from typing import List, Dict, Any
from .interfaces import Vote, FundamentalTool
from .pe_ratio import PERatioTool

REGISTRY: Dict[str, type[FundamentalTool]] = {
    "PE_RATIO": PERatioTool,
}

class FundamentalsPillar:
    def __init__(self, enabled: List[str]):
        self.tools: List[FundamentalTool] = [REGISTRY[name]() for name in enabled if name in REGISTRY]

    def compute_all(self, ticker: str, cfg: Dict[str, Any]) -> List[Vote]:
        votes: List[Vote] = []
        for tool in self.tools:
            if isinstance(tool, PERatioTool):
                votes.append(tool.compute(ticker, **cfg.get("pe_ratio", {})))
        return votes
