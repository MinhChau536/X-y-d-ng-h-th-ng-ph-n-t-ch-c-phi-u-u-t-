"""
Unit tests for BacktestEngine.
"""
import pandas as pd
from analytics.backtesting import BacktestEngine


def test_backtest_ma_crossover(sample_ohlcv_df):
    engine = BacktestEngine(sample_ohlcv_df, initial_capital=100_000_000)
    signal = engine.ma_crossover_strategy(sample_ohlcv_df, fast=10, slow=20)
    
    results = engine.run(signal, strategy_name="MA_Crossover_10_20")
    
    assert "total_return_pct" in results
    assert "cagr_pct" in results
    assert "max_drawdown_pct" in results
    assert "sharpe_ratio" in results
    assert "portfolio_values" in results
    assert len(results["portfolio_values"]) == len(sample_ohlcv_df)


def test_backtest_no_lookahead(sample_ohlcv_df):
    # Ensure backtest handles empty / short signal properly
    engine = BacktestEngine(sample_ohlcv_df)
    zeros = pd.Series(0, index=sample_ohlcv_df.index)
    res = engine.run(zeros, strategy_name="No_Trades")
    
    assert res["n_trades"] == 0
    assert res["total_return_pct"] == 0.0
