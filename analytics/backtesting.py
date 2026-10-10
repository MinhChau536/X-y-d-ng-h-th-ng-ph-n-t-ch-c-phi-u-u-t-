"""
Backtesting engine.

Rules:
  - No look-ahead bias: signals use only data available at time T
  - Financial data cutoff: use only data published before signal date
  - Clearly separate in-sample / out-of-sample periods
  - Report: Return, CAGR, Max Drawdown, Sharpe, Win Rate, Profit Factor
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from analytics.indicators import rsi_wilder
from config.settings import settings

logger = logging.getLogger(__name__)
RISK_FREE_RATE = 0.04  # Vietnamese government bond proxy


class BacktestEngine:
    """
    Event-driven backtester for rule-based strategies.

    Each rule is a callable: rule(df_up_to_t) -> bool
    Signal is generated at close of day T.
    Entry at OPEN of day T+1 (to avoid look-ahead).
    """

    def __init__(
        self,
        price_df: pd.DataFrame,
        initial_capital: float = 100_000_000,  # 100M VND
        commission: float = settings.DEFAULT_TRANSACTION_FEE,
        slippage: float = settings.DEFAULT_SLIPPAGE,
    ):
        self.df = self._prepare(price_df)
        self.initial_capital = initial_capital
        self.commission = commission
        self.slippage = slippage

    @staticmethod
    def _prepare(df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        if "timestamp" in df.columns:
            df = df.set_index("timestamp")
        df.index = pd.to_datetime(df.index)
        return df.sort_index()

    # ─────────────────── Strategy Builders ───────────────────────────────────

    @staticmethod
    def ma_crossover_strategy(df: pd.DataFrame, fast: int = 20, slow: int = 50) -> pd.Series:
        """
        Generate buy/sell signals based on MA crossover.
        Returns a Series of 1 (long), -1 (short/exit), 0 (neutral).
        No look-ahead: uses only data up to each row.
        """
        fast_ma = df["close"].rolling(fast).mean()
        slow_ma = df["close"].rolling(slow).mean()
        signal = pd.Series(0, index=df.index)
        signal[fast_ma > slow_ma] = 1
        signal[fast_ma < slow_ma] = -1
        return signal

    @staticmethod
    def rsi_strategy(df: pd.DataFrame, period: int = 14, ob: float = 70, os: float = 30) -> pd.Series:
        """RSI-based mean-reversion strategy (RSI Wilder, cùng công thức với trang Kỹ thuật)."""
        rsi = rsi_wilder(df["close"], period)
        signal = pd.Series(0, index=df.index)
        signal[rsi < os] = 1   # oversold → buy
        signal[rsi > ob] = -1  # overbought → sell
        return signal

    @staticmethod
    def custom_strategy(
        df: pd.DataFrame,
        price_above_sma50: bool = True,
        sma20_above_sma50: bool = True,
        rsi_min: float = 50,
        rsi_max: float = 70,
        vol_above_ma20: bool = True,
        exit_rsi: float = 80,
    ) -> pd.Series:
        """
        Composite rule-based signal có cả điều kiện VÀO và THOÁT lệnh.

        Vào lệnh (1)  : tất cả điều kiện được bật đều thỏa.
        Thoát lệnh (-1): xu hướng gãy hoặc quá mua, cụ thể là MỘT trong các điều kiện:
            - Giá đóng cửa < SMA50          (nếu điều kiện "Giá > SMA50" được bật)
            - SMA20 < SMA50 (Death Cross)   (nếu điều kiện "SMA20 > SMA50" được bật)
            - RSI > exit_rsi (mặc định 80, chốt lời khi quá mua)
        Khi vừa thỏa điều kiện vào vừa thỏa điều kiện thoát, ưu tiên THOÁT (an toàn hơn).
        Trước đây chiến lược chỉ sinh 1/0 nên đã mua là giữ đến hết kỳ backtest.
        """
        sma20 = df["close"].rolling(20).mean()
        sma50 = df["close"].rolling(50).mean()
        rsi = rsi_wilder(df["close"], 14)
        vol_ma20 = df["volume"].rolling(20).mean() if "volume" in df.columns else None

        entry = pd.Series(True, index=df.index)
        if price_above_sma50:
            entry &= df["close"] > sma50
        if sma20_above_sma50:
            entry &= sma20 > sma50
        entry &= (rsi >= rsi_min) & (rsi <= rsi_max)
        if vol_above_ma20 and vol_ma20 is not None:
            entry &= df["volume"] > vol_ma20

        exit_ = rsi > exit_rsi
        if price_above_sma50:
            exit_ |= df["close"] < sma50
        if sma20_above_sma50:
            exit_ |= sma20 < sma50

        signal = pd.Series(0, index=df.index)
        signal[entry.fillna(False)] = 1
        signal[exit_.fillna(False)] = -1
        return signal

    # ─────────────────── Run Backtest ────────────────────────────────────────

    def run(self, signal: pd.Series, strategy_name: str = "Custom") -> Dict[str, Any]:
        """
        Execute backtest given entry/exit signals.

        Signal convention:
          1 → go long (buy next open)
         -1 → exit (sell next open)
          0 → hold current position

        Returns full trade log and performance metrics.
        """
        df = self.df.copy()
        if df.empty:
            return {"error": "No price data for backtest"}

        if len(signal) == len(df):
            signal = pd.Series(signal.values, index=df.index)
        else:
            signal = signal.reindex(df.index, fill_value=0)

        # Shift signal by 1 to avoid look-ahead (trade on next open)
        shifted_signal = signal.shift(1).fillna(0)

        capital = self.initial_capital
        position = 0  # shares held
        avg_cost = 0.0
        portfolio_values = []
        trades: List[Dict] = []
        in_trade = False
        entry_price = 0.0
        entry_date = None

        for date, row in df.iterrows():
            sig = shifted_signal.loc[date]
            open_price = row.get("open", row["close"])
            close_price = row["close"]

            # Entry
            if sig == 1 and not in_trade and capital > 0:
                buy_price = open_price * (1 + self.slippage)
                shares = int(capital * 0.95 / buy_price / 100) * 100  # round lots
                if shares > 0:
                    cost = shares * buy_price * (1 + self.commission)
                    if cost <= capital:
                        capital -= cost
                        position = shares
                        avg_cost = buy_price
                        entry_price = buy_price
                        entry_date = date
                        in_trade = True

            # Exit
            elif sig == -1 and in_trade and position > 0:
                sell_price = open_price * (1 - self.slippage)
                proceeds = position * sell_price * (1 - self.commission)
                pnl = proceeds - position * avg_cost * (1 + self.commission)
                capital += proceeds
                trades.append({
                    "entry_date": str(entry_date)[:10],
                    "exit_date": str(date)[:10],
                    "entry_price": round(entry_price, 0),
                    "exit_price": round(sell_price, 0),
                    "shares": position,
                    "pnl": round(pnl, 0),
                    "return_pct": round(pnl / (position * avg_cost * (1 + self.commission)) * 100, 2),
                })
                position = 0
                avg_cost = 0.0
                in_trade = False

            portfolio_val = capital + position * close_price
            portfolio_values.append({"date": date, "value": portfolio_val})

        # Close remaining position at last close
        if in_trade and position > 0:
            lp = float(df["close"].iloc[-1])
            proceeds = position * lp * (1 - self.commission)
            pnl = proceeds - position * avg_cost * (1 + self.commission)
            trades.append({
                "entry_date": str(entry_date)[:10],
                "exit_date": str(df.index[-1])[:10],
                "entry_price": round(entry_price, 0),
                "exit_price": round(lp, 0),
                "shares": position,
                "pnl": round(pnl, 0),
                "return_pct": round(pnl / (position * avg_cost * (1 + self.commission)) * 100, 2),
            })
            capital += proceeds

        pv_df = pd.DataFrame(portfolio_values).set_index("date")["value"]
        metrics = self._compute_metrics(pv_df, trades, strategy_name)
        metrics["trade_log"] = trades
        metrics["portfolio_values"] = pv_df.reset_index().to_dict("records")

        return metrics

    def _compute_metrics(
        self, portfolio_values: pd.Series, trades: List[Dict], name: str
    ) -> Dict[str, Any]:
        if portfolio_values.empty:
            return {"error": "No portfolio data"}

        final_val = float(portfolio_values.iloc[-1])
        total_return = (final_val - self.initial_capital) / self.initial_capital * 100

        n_days = max((portfolio_values.index[-1] - portfolio_values.index[0]).days, 1)
        cagr = ((final_val / self.initial_capital) ** (365 / n_days) - 1) * 100

        daily_returns = portfolio_values.pct_change().dropna()
        volatility = float(daily_returns.std() * (252 ** 0.5)) * 100 if len(daily_returns) > 0 else 0
        sharpe = (cagr - RISK_FREE_RATE * 100) / volatility if volatility != 0 else 0

        # Max drawdown
        rolling_max = portfolio_values.cummax()
        drawdown = (portfolio_values - rolling_max) / rolling_max
        max_drawdown = float(drawdown.min()) * 100

        n_trades = len(trades)
        winning_trades = [t for t in trades if t["pnl"] > 0]
        losing_trades = [t for t in trades if t["pnl"] <= 0]
        win_rate = len(winning_trades) / n_trades * 100 if n_trades > 0 else 0
        gross_profit = sum(t["pnl"] for t in winning_trades)
        gross_loss = abs(sum(t["pnl"] for t in losing_trades))
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else float("inf")

        return {
            "strategy_name": name,
            "initial_capital": self.initial_capital,
            "final_value": round(final_val, 0),
            "total_return_pct": round(total_return, 2),
            "cagr_pct": round(cagr, 2),
            "max_drawdown_pct": round(max_drawdown, 2),
            "sharpe_ratio": round(sharpe, 2),
            "volatility_pct": round(volatility, 2),
            "n_trades": n_trades,
            "win_rate_pct": round(win_rate, 1),
            "profit_factor": round(profit_factor, 2),
            "commission": self.commission,
            "slippage": self.slippage,
            "period_days": n_days,
            "warnings": [
                "Kết quả backtest không đảm bảo hiệu quả tương lai",
                "Overfitting: chiến lược được tối ưu trên cùng dữ liệu kiểm định có thể cho kết quả ảo",
                "Chi phí giao dịch thực tế có thể cao hơn giả định",
            ],
        }

    def buy_and_hold_benchmark(self) -> Dict[str, Any]:
        """Compare against a simple Buy & Hold strategy."""
        if self.df.empty:
            return {}
        start_price = float(self.df["close"].iloc[0])
        end_price = float(self.df["close"].iloc[-1])
        n_days = max((self.df.index[-1] - self.df.index[0]).days, 1)
        total_return = (end_price - start_price) / start_price * 100
        cagr = ((end_price / start_price) ** (365 / n_days) - 1) * 100
        daily_ret = self.df["close"].pct_change().dropna()
        vol = float(daily_ret.std() * (252 ** 0.5)) * 100
        sharpe = (cagr - RISK_FREE_RATE * 100) / vol if vol != 0 else 0
        rolling_max = self.df["close"].cummax()
        dd = (self.df["close"] - rolling_max) / rolling_max
        mdd = float(dd.min()) * 100
        return {
            "strategy_name": "Buy & Hold",
            "total_return_pct": round(total_return, 2),
            "cagr_pct": round(cagr, 2),
            "max_drawdown_pct": round(mdd, 2),
            "sharpe_ratio": round(sharpe, 2),
            "volatility_pct": round(vol, 2),
        }
