import pandas as pd
import numpy as np

def _ensure_1d_series(close) -> pd.Series:
    """Coerce array-like/Series/DataFrame 1-col into a 1-D float Series (datetime index if possible)."""
    if isinstance(close, pd.Series):
        s = close
    elif isinstance(close, pd.DataFrame):
        if close.shape[1] == 0:
            return pd.Series(dtype=float)
        s = close.iloc[:, 0]
    else:
        arr = np.asarray(close)
        if arr.ndim == 2 and arr.shape[1] == 1:
            arr = arr[:, 0]
        s = pd.Series(arr)
    s = pd.to_numeric(s, errors="coerce").dropna()
    if not isinstance(s.index, pd.DatetimeIndex):
        try:
            s.index = pd.to_datetime(s.index)
        except Exception:
            pass
    return s.astype(float)
