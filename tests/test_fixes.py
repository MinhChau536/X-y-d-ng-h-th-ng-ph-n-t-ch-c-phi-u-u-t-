"""
Kiểm thử cho 7 điểm đã sửa:
  1. PDF không tự sinh số liệu giả khi thiếu dữ liệu
  2. Điểm rủi ro chuẩn hóa theo thành phần có dữ liệu
  3. Chiến lược Custom có tín hiệu thoát lệnh
  4. Tăng trưởng doanh thu so với cùng kỳ năm trước (YoY), sắp xếp kỳ đúng
  5. Định giá dùng trung vị ngành thật
  6. RSI thống nhất giữa các module
  7. ADX / MFI / OBV / CMF được đưa vào điểm kỹ thuật
"""
import numpy as np
import pandas as pd
import pytest

from analytics.backtesting import BacktestEngine
from analytics.fundamental import FundamentalAnalyzer
from analytics.indicators import rsi_wilder
from analytics.momentum import MomentumAnalyzer
from analytics.opportunity_score import OpportunityScorer
from analytics.peers import compute_peer_stats, find_sector_basket
from analytics.period_utils import growth_vs_prior, parse_period_key
from analytics.technical import TechnicalAnalyzer
from analytics.valuation import ValuationEngine
from reports.pdf_generator import PDFReportGenerator


# ── 6. RSI thống nhất ────────────────────────────────────────────────────────
def test_rsi_same_value_across_modules(sample_ohlcv_df):
    ta = TechnicalAnalyzer(sample_ohlcv_df)
    tech_rsi = float(ta.compute_all()["RSI"].iloc[-1])
    mom_rsi = MomentumAnalyzer(sample_ohlcv_df).compute_rsi()
    bt_rsi = float(rsi_wilder(sample_ohlcv_df["close"], 14).iloc[-1])
    assert tech_rsi == pytest.approx(mom_rsi, abs=1e-9)
    assert tech_rsi == pytest.approx(bt_rsi, abs=1e-9)


def test_rsi_edge_cases():
    up = pd.Series(np.arange(1, 40, dtype=float))
    assert rsi_wilder(up).iloc[-1] == 100.0
    flat = pd.Series([10.0] * 40)
    assert rsi_wilder(flat).iloc[-1] == 50.0
    assert rsi_wilder(up).iloc[:13].isna().all()   # chưa đủ phiên -> NaN, không gán giả


# ── 7. ADX / dòng tiền vào điểm kỹ thuật ─────────────────────────────────────
def test_technical_score_uses_adx_and_money_flow(sample_ohlcv_df):
    ta = TechnicalAnalyzer(sample_ohlcv_df)
    ta.compute_all()
    res = ta.compute_technical_score()
    comps = res["components"]
    assert comps["adx"]["score"] is not None and comps["adx"]["max"] == 10
    assert comps["money_flow"]["score"] is not None and comps["money_flow"]["max"] == 15
    assert {"cmf", "mfi", "obv_above_ma20"} <= set(comps["money_flow"])
    # 100 phiên < 200 nên SMA200 thiếu -> mẫu số chỉ còn 15 điểm cho MA
    assert comps["ma_alignment"]["max"] == 15
    assert res["max_raw"] == 90


# ── 2. Điểm rủi ro ───────────────────────────────────────────────────────────
def test_risk_score_reaches_100_with_partial_data():
    r = OpportunityScorer.compute_risk_score(volatility_30d=0.005, max_drawdown=-0.05)
    assert r["score"] == 100            # trước khi sửa: tối đa 60
    assert r["coverage_pts"] == 60


def test_risk_score_none_when_no_data():
    assert OpportunityScorer.compute_risk_score()["score"] is None


# ── 3. Custom strategy có thoát lệnh ─────────────────────────────────────────
def test_custom_strategy_has_exit_signals():
    n = 260
    t = np.arange(n)
    close = 100 + 15 * np.sin(t / 20) + t * 0.05          # nhiều chu kỳ tăng/giảm
    df = pd.DataFrame({
        "timestamp": pd.date_range("2024-01-01", periods=n, freq="B"),
        "open": close, "high": close * 1.01, "low": close * 0.99, "close": close,
        "volume": 1_000_000 + (t % 7) * 200_000,
    })
    eng = BacktestEngine(df)
    sig = eng.custom_strategy(eng.df, rsi_min=40, rsi_max=90, vol_above_ma20=False)
    assert (sig == -1).any() and (sig == 1).any()
    res = eng.run(sig, "Custom")
    # Có ít nhất một lệnh được đóng TRƯỚC phiên cuối (không phải giữ đến hết kỳ)
    last_day = str(eng.df.index[-1])[:10]
    assert any(tr["exit_date"] != last_day for tr in res["trade_log"])


# ── 4. Tăng trưởng YoY & thứ tự kỳ ───────────────────────────────────────────
def test_parse_period_key():
    assert parse_period_key("2024-Q3") == 20243
    assert parse_period_key("Q1/2025") == 20251
    assert parse_period_key("2023") == 20230


def test_revenue_growth_is_yoy_even_if_source_is_newest_first():
    # Nguồn trả kỳ MỚI NHẤT ĐỨNG ĐẦU (như VCI). Doanh thu có tính mùa vụ quý 4.
    rows = [
        (2025, 2, 130), (2025, 1, 110), (2024, 4, 200), (2024, 3, 120),
        (2024, 2, 100), (2024, 1, 90),
    ]
    is_df = pd.DataFrame({
        "Năm": [r[0] for r in rows], "Kỳ": [r[1] for r in rows],
        "Doanh thu thuần": [r[2] for r in rows],
        "Lợi nhuận sau thuế": [r[2] / 10 for r in rows],
    })
    fa = FundamentalAnalyzer(is_df, None, None)
    rp = fa.get_revenue_profit_trend()
    assert rp["revenue_latest"] == 130               # Q2/2025 là kỳ mới nhất
    assert rp["latest_period"] == "Q2/2025"
    assert rp["compare_period"] == "Q2/2024"
    assert rp["revenue_yoy"] == pytest.approx(30.0)  # 130 vs 100, không phải vs 110 (QoQ)
    assert rp["revenue_growth_basis"].startswith("YoY")
    assert rp["periods"][0] == "Q1/2024"


def test_matrix_format_period_columns_ordered():
    df = pd.DataFrame({
        "item": ["Doanh thu thuần"],
        "Q4/2024": [200.0], "Q1/2025": [110.0], "Q1/2024": [90.0],
    })
    s = FundamentalAnalyzer(df, None, None)._series(df, ["doanh thu"])
    g = growth_vs_prior(s)
    assert g["latest_period"] == "Q1/2025"
    assert g["pct"] == pytest.approx((110 - 90) / 90 * 100)


# ── 5. Định giá theo trung vị ngành ──────────────────────────────────────────
def _ratio(pe, pb, roe=0.18):
    return pd.DataFrame({"Năm": [2025], "Kỳ": [2], "P/E": [pe], "P/B": [pb], "ROE (%)": [roe]})


def test_peer_stats_and_sector_based_valuation():
    assert find_sector_basket("FPT") is not None
    fake = {"CMG": _ratio(20, 3), "FOX": _ratio(14, 4), "ELC": _ratio(30, 2),
            "CTR": _ratio(25, 5), "VGI": _ratio(500, 1)}       # 500 là ngoại lai, bị loại
    stats = compute_peer_stats("FPT", lambda s: fake.get(s, pd.DataFrame()))
    assert stats["pe"] == pytest.approx(22.5)                    # median(20,14,30,25)
    assert stats["n_pe"] == 4

    ve = ValuationEngine("FPT", 100_000, ratio_df=_ratio(18, 4.5), peer_stats=stats)
    rel = ve.relative_valuation()
    assert rel["sector_pe"] == pytest.approx(22.5)
    assert "Trung vị" in rel["sector_pe_source"]
    vs = ve.compute_valuation_score()
    assert vs["components"]["pe"]["vs_sector"] == pytest.approx(18 / 22.5, abs=0.01)


def test_valuation_without_peers_is_labelled_default():
    rel = ValuationEngine("XYZ", 50_000, ratio_df=_ratio(10, 1)).relative_valuation()
    assert rel["sector_pe"] == 15.0
    assert "Mặc định" in rel["sector_pe_source"]


# ── 1. PDF không bịa số ─────────────────────────────────────────────────────
def test_pdf_has_no_fabricated_values_when_data_missing():
    gen = PDFReportGenerator()
    data, a = gen._prepare_data({"symbol": "ABC", "current_price": {"price": 25000}})
    assert a["px"] is None
    assert a["total"] is None and a["rec"] == "CHƯA ĐỦ DỮ LIỆU"
    assert a["target"] is None and a["stop"] is None and a["upside"] is None
    assert a["last_roe"] is None and a["fin"].empty
    assert data["news_items"] == [] and data["peers"] == {}
    assert all(v is None for v in a["scores"].values())


def test_pdf_full_pipeline_uses_real_components(sample_ohlcv_df, tmp_path):
    ta = TechnicalAnalyzer(sample_ohlcv_df)
    enriched = ta.compute_all()
    tech_score = ta.compute_technical_score()
    analysis = {
        "symbol": "FPT",
        "current_price": {"price": float(sample_ohlcv_df["close"].iloc[-1])},
        "technical": {"available": True, "data": enriched, "signals": ta.get_signals(), "score": tech_score},
        "opportunity_score": {"composite": {"score": 61, "coverage_pct": 25},
                              "sub_scores": {"technical": tech_score["score"]}},
        "index_history": pd.DataFrame(),
    }
    gen = PDFReportGenerator()
    _, a = gen._prepare_data(analysis)
    tech_rows = dict(a["checks"])[f"3. Kỹ thuật – {tech_score['score']}/100"]
    assert sum(r["pts"] or 0 for r in tech_rows) == tech_score["total_raw"]
    assert a["stop"] is not None                       # có ATR thật -> có cắt lỗ
    pdf = gen.generate(analysis, report_type="test", output_path=str(tmp_path / "t.pdf"))
    assert pdf.startswith(b"%PDF")
