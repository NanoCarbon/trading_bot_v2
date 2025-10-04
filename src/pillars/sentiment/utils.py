import math
from typing import Optional

def exp_decay_weight(age_days: float, half_life_days: float = 3.0) -> float:
    """Exponential decay weight in [0,1], with configurable half-life."""
    if half_life_days <= 0:
        return 1.0
    lam = math.log(2) / half_life_days
    return float(math.exp(-lam * max(0.0, age_days)))

def clamp01(x: Optional[float]) -> float:
    if x is None or x != x:  # NaN check
        return 0.0
    return float(min(1.0, max(0.0, x)))
