"""
Pytest fixtures for Stock Analytics Pro.
"""
import os
import tempfile

# Kiểm thử luôn chạy trên CSDL bộ nhớ & thư mục tạm – không đụng dữ liệu thật của người dùng
_TMP = tempfile.mkdtemp(prefix="gpm_test_")
os.environ.setdefault("DB_PATH", ":memory:")
os.environ.setdefault("CACHE_DIR", os.path.join(_TMP, "cache"))
os.environ.setdefault("REPORTS_DIR", os.path.join(_TMP, "reports"))
os.environ.setdefault("DOCUMENTS_DIR", os.path.join(_TMP, "documents"))

import pytest
import numpy as np
import pandas as pd
from datetime import datetime, timedelta


@pytest.fixture
def sample_ohlcv_df():
    """Generate 100 days of synthetic realistic OHLCV price data."""
    dates = pd.date_range(end=datetime.now(), periods=100, freq="B")
    np.random.seed(42)
    base_price = 100000.0
    returns = np.random.normal(0.001, 0.015, size=len(dates))
    prices = base_price * np.exp(np.cumsum(returns))
    
    highs = prices * (1 + np.abs(np.random.normal(0, 0.008, size=len(dates))))
    lows = prices * (1 - np.abs(np.random.normal(0, 0.008, size=len(dates))))
    opens = prices * (1 + np.random.normal(0, 0.005, size=len(dates)))
    volumes = np.random.randint(500000, 3000000, size=len(dates))
    
    df = pd.DataFrame({
        "timestamp": dates,
        "symbol": "FPT",
        "open": opens,
        "high": highs,
        "low": lows,
        "close": prices,
        "volume": volumes,
        "value": prices * volumes,
    })
    return df


@pytest.fixture
def sample_financial_ratios():
    """Sample financial metrics for testing fundamental and valuation analyzers."""
    return {
        "symbol": "FPT",
        "pe": 16.5,
        "pb": 3.8,
        "roe": 26.5,
        "roa": 12.4,
        "eps": 6200.0,
        "bvps": 28000.0,
        "debt_equity": 0.65,
        "net_margin": 16.8,
        "revenue_growth": 19.5,
        "profit_growth": 21.2,
        "fcf": 4500000000000.0,  # 4,500 tỷ
        "shares_outstanding": 1270000000,
    }


@pytest.fixture
def fake_repo():
    """DataRepository với các nguồn giả lập (không gọi mạng, không dùng cache)."""
    from data.data_repository import DataRepository
    from tests.fakes import FakeDNSE, FakeVietstock, FakeVnstock
    return DataRepository(vnstock_client=FakeVnstock(), dnse_client=FakeDNSE(),
                          vietstock_client=FakeVietstock(True), pdf_financial_loader=lambda s, p: pd.DataFrame(),
                          use_cache=False)
