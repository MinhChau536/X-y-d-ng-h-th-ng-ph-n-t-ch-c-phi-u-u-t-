"""
Momentum analysis.

Computes multi-period momentum, relative strength vs VN-Index,
and a Momentum Score 0–100.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

from analytics.indicators import rsi_wilder

logger = logging.getLogger(__name__)


class MomentumAnalyzer:
    """
    Compute momentum indicators and relative strength.

    Parameters
    ----------
    price_df  : Stock OHLCV DataFrame
    index_df  : VN-Index OHLCV DataFrame (for relative strength)
    """

    def __init__(self, price_df: pd.DataFrame, index_df: pd.DataFrame = None):
        self.df = self._prepare(price_df)
        self.idx_df = self._prepare(index_df) if index_df is not None else pd.DataFrame()

    @staticmethod
    def _prepare(df: pd.DataFrame) -> pd.DataFrame:
        if df is None or df.empty:
            return pd.DataFrame()
        df = df.copy()
        if "timestamp" in df.columns:
            df = df.set_index("timestamp")
        df.index = pd.to_datetime(df.index)
        return df.sort_index()

    # ─────────────────── Price Momentum ──────────────────────────────────────

    def price_momentum(self, periods: List[int] = [5, 10, 20, 60, 120]) -> Dict[str, Optional[float]]:
        """Return price returns over multiple periods."""
        if self.df.empty or "close" not in self.df.columns:
            return {}
        closes = self.df["close"].dropna()
        result = {}
        current = float(closes.iloc[-1])
        for p in periods:
            if len(closes) > p:
                past = float(closes.iloc[-p - 1])
                result[f"momentum_{p}d"] = (current - past) / past * 100 if past != 0 else None
            else:
                result[f"momentum_{p}d"] = None
        return result

    # ─────────────────── Relative Strength vs VN-Index ───────────────────────

    def relative_strength(self, period: int = 60) -> Dict[str, Any]:
        """Compute RS ratio and RS score vs VN-Index."""
        if self.df.empty or self.idx_df.empty:
            return {"available": False, "reason": "Không có dữ liệu VN-Index"}
        if "close" not in self.df.columns or "close" not in self.idx_df.columns:
            return {"available": False}

        # Align on common dates
        stock_closes = self.df["close"].dropna()
        index_closes = self.idx_df["close"].dropna()
        common = stock_closes.index.intersection(index_closes.index)
        if len(common) < period:
            return {"available": False, "reason": "Không đủ dữ liệu tương thích"}

        stock_s = stock_closes.loc[common].tail(period)
        index_s = index_closes.loc[common].tail(period)

        stock_ret = float(stock_s.iloc[-1] / stock_s.iloc[0] - 1) * 100
        index_ret = float(index_s.iloc[-1] / index_s.iloc[0] - 1) * 100
        rs_diff = stock_ret - index_ret

        # RS ratio (Mansfield-style simplified)
        rs_ratio = stock_s / index_s
        rs_normalized = (rs_ratio - rs_ratio.mean()) / rs_ratio.std() if rs_ratio.std() != 0 else rs_ratio - rs_ratio.mean()

        return {
            "available": True,
            "period": period,
            "stock_return": round(stock_ret, 2),
            "index_return": round(index_ret, 2),
            "rs_differential": round(rs_diff, 2),
            "outperforming": rs_diff > 0,
            "rs_trend": "Mạnh hơn thị trường" if rs_diff > 0 else "Yếu hơn thị trường",
        }

    # ─────────────────── RSI from price data ─────────────────────────────────

    def compute_rsi(self, period: int = 14) -> Optional[float]:
        """RSI Wilder – dùng chung hàm với TechnicalAnalyzer và Backtest."""
        if self.df.empty or "close" not in self.df.columns:
            return None
        closes = self.df["close"].dropna()
        if len(closes) < period + 1:
            return None
        rsi = rsi_wilder(closes, period)
        return float(rsi.iloc[-1]) if pd.notna(rsi.iloc[-1]) else None

    # ─────────────────── Momentum Score ──────────────────────────────────────

    def compute_momentum_score(self) -> Dict[str, Any]:
        """
        Score momentum 0–100.

        Components:
          Short-term momentum 5/10d  (25)
          Medium-term momentum 20d   (20)
          Long-term momentum 60/120d (20)
          Relative strength          (20)
          RSI zone                   (15)
        """
        components: Dict[str, Any] = {}
        total = 0.0
        max_pts = 0
        missing = []

        mom = self.price_momentum()

        # ── Short momentum (25) ──
        max_pts += 25
        m5 = mom.get("momentum_5d")
        m10 = mom.get("momentum_10d")
        if m5 is not None or m10 is not None:
            val = (m5 or 0) * 0.4 + (m10 or 0) * 0.6
            if val > 5:
                s = 25
            elif val > 2:
                s = 18
            elif val > 0:
                s = 12
            elif val > -2:
                s = 6
            else:
                s = 0
            components["short_momentum"] = {"score": s, "max": 25, "value": round(val, 2)}
            total += s
        else:
            missing.append("Động lượng ngắn hạn")
            components["short_momentum"] = {"score": None, "max": 25}

        # ── Medium momentum (20) ──
        max_pts += 20
        m20 = mom.get("momentum_20d")
        if m20 is not None:
            if m20 > 10:
                s = 20
            elif m20 > 3:
                s = 14
            elif m20 > 0:
                s = 8
            elif m20 > -5:
                s = 4
            else:
                s = 0
            components["medium_momentum"] = {"score": s, "max": 20, "value": round(m20, 2)}
            total += s
        else:
            missing.append("Động lượng trung hạn")
            components["medium_momentum"] = {"score": None, "max": 20}

        # ── Long momentum (20) ──
        max_pts += 20
        m60 = mom.get("momentum_60d")
        m120 = mom.get("momentum_120d")
        if m60 is not None or m120 is not None:
            val = (m60 or 0) * 0.5 + (m120 or 0) * 0.5
            if val > 20:
                s = 20
            elif val > 5:
                s = 14
            elif val > 0:
                s = 8
            elif val > -10:
                s = 4
            else:
                s = 0
            components["long_momentum"] = {"score": s, "max": 20, "value": round(val, 2)}
            total += s
        else:
            missing.append("Động lượng dài hạn")
            components["long_momentum"] = {"score": None, "max": 20}

        # ── Relative Strength (20) ──
        max_pts += 20
        rs = self.relative_strength()
        if rs.get("available"):
            rs_diff = rs.get("rs_differential", 0)
            if rs_diff > 10:
                s = 20
            elif rs_diff > 3:
                s = 15
            elif rs_diff > 0:
                s = 10
            elif rs_diff > -5:
                s = 5
            else:
                s = 0
            components["relative_strength"] = {"score": s, "max": 20, "value": round(rs_diff, 2)}
            total += s
        else:
            missing.append("Sức mạnh tương đối")
            components["relative_strength"] = {"score": None, "max": 20}

        # ── RSI zone (15) ──
        max_pts += 15
        rsi = self.compute_rsi()
        if rsi is not None:
            if 50 <= rsi <= 70:
                s = 15
            elif 40 <= rsi < 50 or 70 < rsi <= 80:
                s = 8
            elif rsi > 80 or rsi < 30:
                s = 2
            else:
                s = 5
            components["rsi_zone"] = {"score": s, "max": 15, "value": round(rsi, 1)}
            total += s
        else:
            missing.append("RSI")
            components["rsi_zone"] = {"score": None, "max": 15}

        available_max = sum(c["max"] for c in components.values() if c.get("score") is not None)
        available_total = sum(c["score"] for c in components.values() if c.get("score") is not None)

        if available_max == 0:
            final_score = None
            state = "Không đủ dữ liệu"
        else:
            final_score = round((available_total / available_max) * 100)
            if final_score >= 70:
                state = "Động lượng mạnh"
            elif final_score >= 55:
                state = "Động lượng tích cực"
            elif final_score >= 40:
                state = "Trung tính"
            else:
                state = "Động lượng yếu"

        return {
            "score": final_score,
            "state": state,
            "components": components,
            "momentum_periods": mom,
            "relative_strength": rs,
            "rsi": rsi,
            "missing_data": missing,
        }
