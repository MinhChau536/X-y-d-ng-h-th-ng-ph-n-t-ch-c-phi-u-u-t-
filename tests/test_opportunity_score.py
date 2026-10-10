"""
Unit tests for OpportunityScorer.
"""
from analytics.opportunity_score import OpportunityScorer


def test_scorer_all_dimensions():
    scorer = OpportunityScorer()
    res = scorer.compute(
        technical_score=80.0,
        momentum_score=75.0,
        fundamental_score=85.0,
        valuation_score=70.0,
        risk_score=90.0,
    )
    
    assert "score" in res
    score = res["score"]
    assert 0 <= score <= 100
    assert "classification" in res
    assert "label" in res["classification"]
    assert "color" in res["classification"]
    assert res["coverage_pct"] == 100


def test_scorer_with_missing_groups():
    scorer = OpportunityScorer()
    res = scorer.compute(
        technical_score=70.0,
        momentum_score=None,
        fundamental_score=80.0,
        valuation_score=None,
        risk_score=70.0,
    )
    
    # Check that score is re-weighted without failing
    assert "score" in res
    score = res["score"]
    assert 0 <= score <= 100
    assert res["coverage_pct"] < 100
