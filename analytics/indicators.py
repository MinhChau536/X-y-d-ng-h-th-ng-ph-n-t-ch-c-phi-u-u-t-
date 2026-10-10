"""
Shared indicator primitives.

Mọi module (kỹ thuật, động lượng, backtest) dùng CHUNG các hàm ở đây để cùng
một mã cổ phiếu luôn cho ra cùng một giá trị chỉ báo.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def rsi_wilder(close: pd.Series, period: int = 14) -> pd.Series:
    """
    RSI theo phương pháp gốc của J. Welles Wilder (1978).

    avg_gain, avg_loss được làm mượt bằng RMA (EWM với alpha = 1/period),
    đây cũng là cách pandas-ta / TradingView / Amibroker tính RSI.

    Quy ước biên:
      - Chưa đủ `period` phiên  -> NaN (không gán giá trị giả)
      - avg_loss = 0, avg_gain > 0 -> 100
      - avg_loss = 0, avg_gain = 0 -> 50 (giá đi ngang tuyệt đối)
    """
    close = pd.to_numeric(close, errors="coerce")
    delta = close.diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)
    alpha = 1.0 / period
    avg_gain = gain.ewm(alpha=alpha, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=alpha, min_periods=period, adjust=False).mean()

    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100.0 - (100.0 / (1.0 + rs))

    ready = avg_gain.notna() & avg_loss.notna()
    rsi = rsi.where(~(ready & (avg_loss == 0) & (avg_gain > 0)), 100.0)
    rsi = rsi.where(~(ready & (avg_loss == 0) & (avg_gain == 0)), 50.0)
    return rsi
