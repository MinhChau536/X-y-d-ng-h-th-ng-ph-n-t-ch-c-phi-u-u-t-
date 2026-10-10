"""
Unit tests for TechnicalAnalyzer.
"""
from analytics.technical import TechnicalAnalyzer


def test_technical_indicators_calculation(sample_ohlcv_df):
    analyzer = TechnicalAnalyzer(sample_ohlcv_df)
    enriched = analyzer.compute_all()
    
    # Assert columns added
    assert "SMA_20" in enriched.columns
    assert "SMA_50" in enriched.columns
    assert "EMA_12" in enriched.columns
    assert "RSI" in enriched.columns
    assert "MACD" in enriched.columns
    assert "MACD_signal" in enriched.columns
    assert "BB_upper" in enriched.columns
    assert "BB_lower" in enriched.columns
    assert "ATR" in enriched.columns
    assert "OBV" in enriched.columns
    
    # Check RSI range [0, 100]
    valid_rsi = enriched["RSI"].dropna()
    assert len(valid_rsi) > 0
    assert (valid_rsi >= 0).all() and (valid_rsi <= 100).all()


def test_signals_detection(sample_ohlcv_df):
    analyzer = TechnicalAnalyzer(sample_ohlcv_df)
    analyzer.compute_all()
    signals = analyzer.get_signals()
    
    assert "trend" in signals
    assert "rsi" in signals
    assert "macd" in signals
    assert "bollinger" in signals
    assert "support_resistance" in signals
    assert isinstance(signals["trend"]["score"], (int, float))


def test_technical_scoring_bounds(sample_ohlcv_df):
    analyzer = TechnicalAnalyzer(sample_ohlcv_df)
    analyzer.compute_all()
    score_res = analyzer.compute_technical_score()
    
    assert "score" in score_res
    score = score_res["score"]
    assert 0 <= score <= 100
