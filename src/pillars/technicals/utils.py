import pandas as pd
import numpy as np

def _ensure_1d_series(close) -> pd.Series:
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

def rsi_from_close(close, period: int = 14) -> pd.Series:
    s = _ensure_1d_series(close)
    if s.empty:
        return pd.Series(dtype=float)
    delta = s.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1/period, adjust=False, min_periods=period).mean()
    avg_loss = loss.ewm(alpha=1/period, adjust=False, min_periods=period).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))

def sma(series: pd.Series, window: int) -> pd.Series:
    s = _ensure_1d_series(series)
    return s.rolling(window=window, min_periods=window).mean()
