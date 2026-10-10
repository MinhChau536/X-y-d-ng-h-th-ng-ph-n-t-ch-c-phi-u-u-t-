"""
Unit tests for ValuationEngine.
"""
import pytest
import pandas as pd
from analytics.valuation import ValuationEngine


def test_relative_valuation(sample_financial_ratios):
    ratio_df = pd.DataFrame([{
        "symbol": "FPT",
        "pe": sample_financial_ratios["pe"],
        "pb": sample_financial_ratios["pb"],
        "eps": sample_financial_ratios["eps"],
        "bvps": sample_financial_ratios["bvps"],
    }])
    
    current_price = 100000.0
    engine = ValuationEngine(
        symbol="FPT",
        current_price=current_price,
        ratio_df=ratio_df,
    )
    
    res = engine.relative_valuation()
    assert res["pe"] == pytest.approx(16.5, 0.1)
    assert res["pb"] == pytest.approx(3.8, 0.1)
    assert "pe_fair_value" in res
    assert "pb_fair_value" in res
    assert "average_fair_value" in res
    assert res["pe_fair_value"] == pytest.approx(sample_financial_ratios["eps"] * 15.0)


def test_dcf_valuation_scenarios(sample_financial_ratios):
    ratio_df = pd.DataFrame([{
        "eps": sample_financial_ratios["eps"],
    }])
    engine = ValuationEngine(
        symbol="FPT",
        current_price=100000.0,
        ratio_df=ratio_df,
    )
    
    dcf = engine.dcf_valuation(growth_rate=0.12, discount_rate=0.11)
    assert dcf["available"] is True
    assert "scenarios" in dcf
    assert "Cơ sở" in dcf["scenarios"]
    assert "Thận trọng" in dcf["scenarios"]
    assert "Lạc quan" in dcf["scenarios"]
    # Check bull > base > bear
    sc = dcf["scenarios"]
    assert sc["Lạc quan"] >= sc["Cơ sở"] >= sc["Thận trọng"]
