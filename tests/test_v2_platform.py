"""
Kiểm thử nền tảng v2: nguồn dữ liệu lai ghép, BCTC nhiều nguồn, bộ chuẩn hóa, bộ tính chỉ số,
trích BCTC từ PDF, kho tài liệu, cảnh báo, bộ lọc, Excel, PDF theo mục, an toàn đa luồng.
Mọi dữ liệu là GIẢ LẬP theo đúng định dạng thật của vnstock 4.x – không gọi mạng.
"""
import io
import threading

import numpy as np
import pandas as pd
import pytest

from analytics import financial_ratios as fr
from data.data_repository import DataRepository, merge_financial_sources, stitch_prices, to_vnd
from data.financial_mapping import canonicalize, infer_scale
from data.pdf_financial_extractor import extract_financials
from data.providers.dnse_client import DNSEClient
from data.providers.vietstock_client import VietstockClient
from tests.fakes import FakeDNSE, FakeVietstock, FakeVnstock, kbs_income, price_frame, vci_income
from tests.pdf_samples import make_vas_pdf


# ── Bộ chuẩn hóa BCTC ────────────────────────────────────────────────────────

def test_canonical_vci_matrix_picks_net_revenue_not_growth_row():
    w = canonicalize(vci_income(), "is")
    assert list(w.index) == sorted(w.index)                    # kỳ tăng dần dù nguồn để mới nhất trước
    assert w.loc[20250, "revenue"] == pytest.approx(30_000e9 * 1.15 ** 5)   # dòng "Doanh thu thuần"
    assert w.loc[20250, "net_income_parent"] < w.loc[20250, "net_income"]
    assert "2025_1" not in map(str, w.index)                    # cột trùng bị bỏ


def test_canonical_kbs_ids_and_v3_tabular_units():
    k = canonicalize(kbs_income(), "is")
    assert {"revenue", "net_income", "selling_expense"} <= set(k.columns)
    v3 = pd.DataFrame({"CP": ["FPT"] * 2, "Năm": [2024, 2023], "Kỳ": [5, 5],
                       "Tăng trưởng doanh thu (%)": [0.2, 0.1], "Doanh thu (Tỷ đồng)": [62000, 52000]})
    w = canonicalize(v3, "is")
    assert w.loc[20240, "revenue"] == 62000e9                   # "(Tỷ đồng)" → ×1e9


def test_infer_scale():
    assert infer_scale(pd.DataFrame({"total_assets": [50_000.0]})) == 1e6     # 50.000 triệu = 50 tỷ
    assert infer_scale(pd.DataFrame({"total_assets": [7e13]})) == 1.0


# ── Giá lai ghép DNSE + lịch sử ──────────────────────────────────────────────

def test_to_vnd_scales_stocks_not_indices():
    df = price_frame("2025-01-01", "2025-02-01", base=100.0)
    assert to_vnd(df, "FPT")["close"].median() > 1000
    assert to_vnd(df, "VNINDEX")["close"].median() < 1000


def test_stitch_prices_adjusts_older_segment():
    recent = price_frame("2025-06-01", "2025-08-01", base=100.0, source="dnse")
    older = recent.copy()
    older["close"] = older["close"] / 2          # nguồn cũ chưa điều chỉnh chia tách 2:1
    older = pd.concat([price_frame("2025-01-01", "2025-05-30", base=50.0), older], ignore_index=True)
    out, k = stitch_prices(recent, older)
    assert k == pytest.approx(2.0)
    assert out["timestamp"].is_monotonic_increasing and not out["timestamp"].duplicated().any()
    _, k2 = stitch_prices(recent, recent.copy())
    assert k2 is None


def test_hybrid_price_uses_dnse_recent_and_history_older(fake_repo):
    df = fake_repo.get_price_history("FPT", days=800)
    srcs = [p["source"] for p in df.attrs["provenance"]]
    assert "dnse" in srcs and any(s.startswith("vnstock") for s in srcs)
    assert df[df["source"] == "dnse"]["timestamp"].min() > df[df["source"] != "dnse"]["timestamp"].max()
    assert df["close"].median() > 1000                          # quy về VND


def test_price_falls_back_when_dnse_or_vnstock_fails():
    r = DataRepository(vnstock_client=FakeVnstock(), dnse_client=FakeDNSE(fail=True),
                       vietstock_client=FakeVietstock(), use_cache=False)
    assert set(r.get_price_history("FPT", days=100)["source"]) == {"vnstock_vci"}
    r2 = DataRepository(vnstock_client=FakeVnstock(fail_price=True), dnse_client=FakeDNSE(fail=True),
                        vietstock_client=FakeVietstock(True), use_cache=False)
    assert set(r2.get_price_history("FPT", days=100)["source"]) == {"vietstock"}


# ── BCTC nhiều nguồn ─────────────────────────────────────────────────────────

def test_financials_merge_sources_and_track_provenance(fake_repo):
    fin = fake_repo.get_financials("FPT", "year", years=10)
    d, s = fin["data"], fin["sources"]
    assert 20190 in d.index and s.loc[20190, "cfo"] == "vietstock"        # Vietstock bù năm VCI không có
    assert s.loc[20250, "revenue"] == "vnstock_vci"
    assert s.loc[20250, "selling_expense"] == "vnstock_kbs"               # KBS bù chỉ tiêu VCI thiếu
    assert all(int(k) % 10 == 0 for k in d.index)                         # chỉ kỳ năm
    assert d.loc[20250, "shares_outstanding"] == 1.2e9                    # từ bảng chỉ số theo quý → năm


def test_financials_fallback_to_kbs_when_vci_missing():
    r = DataRepository(vnstock_client=FakeVnstock(fail_vci_fin=True), dnse_client=FakeDNSE(),
                       vietstock_client=FakeVietstock(), pdf_financial_loader=lambda s, p: pd.DataFrame(),
                       use_cache=False)
    fin = r.get_financials("FPT", "year")
    assert set(fin["sources"]["revenue"].dropna()) == {"vnstock_kbs"}


def test_quarter_mode_maps_year_end_balances_to_q4(fake_repo):
    q = fake_repo.get_financials("FPT", "quarter", years=3)["data"]
    assert all(int(k) % 10 > 0 for k in q.index)
    assert pd.notna(q.loc[20254, "total_assets"]) and pd.isna(q.loc[20253].get("total_assets"))


def test_merge_priority():
    a = pd.DataFrame({"x": [1.0, np.nan]}, index=[20240, 20250])
    b = pd.DataFrame({"x": [9.0, 2.0]}, index=[20240, 20250])
    v, s = merge_financial_sources([("A", a), ("B", b)])
    assert v["x"].tolist() == [1.0, 2.0] and s["x"].tolist() == ["A", "B"]


# ── Bộ tính chỉ số từ BCTC ───────────────────────────────────────────────────

@pytest.fixture
def hand_data():
    return pd.DataFrame({
        "revenue": [1000., 1200.], "cogs": [-600., -700.], "gross_profit": [400., 500.], "operating_profit": [150., 200.],
        "profit_before_tax": [140., 190.], "interest_expense": [-10., -10.], "income_tax": [28., 38.],
        "net_income": [112., 152.], "net_income_parent": [100., 140.], "depreciation": [50., 60.],
        "cfo": [130., 180.], "capex": [-40., -60.], "dividends_paid": [-30., -50.],
        "total_assets": [2000., 2400.], "equity": [1000., 1200.], "total_liabilities": [1000., 1200.],
        "current_assets": [800., 1000.], "current_liabilities": [500., 550.], "inventory": [200., 240.],
        "receivables": [150., 180.], "payables": [100., 120.], "cash": [100., 150.],
        "short_term_debt": [200., 220.], "long_term_debt": [300., 280.], "minority_interest": [50., 60.],
        "retained_earnings": [300., 380.], "shares_outstanding": [10., 10.]}, index=[20240, 20250])


def test_ratios_match_hand_calculation(hand_data):
    r = fr.compute_ratios(hand_data, "year").loc[20250]
    assert r["roe"] == pytest.approx(140 / ((950 + 1140) / 2) * 100)       # LNST mẹ / VCSH mẹ bình quân
    assert r["roa"] == pytest.approx(152 / 2200 * 100)
    assert r["gross_margin"] == pytest.approx(500 / 1200 * 100)
    assert r["interest_coverage"] == pytest.approx(20.0)
    assert r["current_ratio"] == pytest.approx(1000 / 550)
    assert r["debt_to_equity"] == pytest.approx(500 / 1200)
    assert r["revenue_growth"] == pytest.approx(20.0)
    assert r["eps"] == pytest.approx(14.0) and r["bvps"] == pytest.approx(114.0)
    assert r["fcf"] == pytest.approx(120.0)


def test_valuation_and_health_scores(hand_data):
    v = fr.valuation_snapshot(hand_data, price=200.0, period="year")
    assert v["pe"] == pytest.approx(200 / 14) and v["pb"] == pytest.approx(200 / 114)
    assert v["enterprise_value"] == pytest.approx(2000 + 500 - 150 + 60)
    z = fr.altman_z(hand_data)
    assert z["score"] == pytest.approx(3.25 + 6.56 * 450 / 2400 + 3.26 * 380 / 2400 + 6.72 * 200 / 2400 + 1.05 * 1.0, abs=0.01)
    p = fr.piotroski(hand_data)
    assert p["max"] == 9 and 0 <= p["score"] <= 9


def test_ttm_requires_four_consecutive_quarters():
    s = pd.Series([1., 2., 3., 4., 5.], index=[20244, 20251, 20252, 20253, 20254])
    t = fr._ttm(s)
    assert pd.isna(t.loc[20252]) and t.loc[20253] == 10.0 and t.loc[20254] == 14.0
    gap = pd.Series([1., 2., 4., 5.], index=[20244, 20251, 20253, 20254])     # thiếu Q2/2025
    assert fr._ttm(gap).isna().all()


# ── PDF BCTC theo mã số VAS ──────────────────────────────────────────────────

def test_pdf_extraction_vas_codes():
    res = extract_financials(make_vas_pdf())
    v = res["values"]
    assert res["unit"] == 1e6 and res["checks"]["balance_identity"] and res["checks"]["assets_equal_sources"]
    assert v["revenue"] == 60_300e6 and v["cogs"] == -37_400e6 and v["interest_expense"] == -720e6
    assert v["total_assets"] == 70_500e6 and v["charter_capital"] == 12_700e6 and v["cfo"] == 11_900e6
    assert v["eps"] == 5986                                    # EPS không nhân đơn vị
    assert v["revenue"] != 999_999e6                           # dòng trong phần thuyết minh bị bỏ qua


def test_document_classification_and_pdf_as_last_source(tmp_path):
    from data.database import Database
    from services.document_service import DocumentService, classify_document
    assert classify_document("Báo cáo thường niên 2024")["doc_type"] == "annual_report"
    q = classify_document("Báo cáo tài chính riêng Quý 3 năm 2025")
    assert (q["doc_type"], q["quarter"], q["consolidated"]) == ("fs_quarterly", 3, False)

    db = Database(":memory:")
    ds = DocumentService(db=db, base_dir=tmp_path)
    ds.save_upload("ABC", "BCTC_hop_nhat_2025.pdf", make_vas_pdf(), "fs_annual", 2025)
    wide = ds.pdf_financials("ABC", "year")
    assert wide.loc[20250, "revenue"] == 60_300e6

    r = DataRepository(vnstock_client=FakeVnstock(fail_vci_fin=True), dnse_client=FakeDNSE(),
                       vietstock_client=FakeVietstock(), pdf_financial_loader=ds.pdf_financials, use_cache=False)
    fin = r.get_financials("ABC", "year")
    assert fin["sources"].loc[20250, "total_assets"] == "pdf"   # KBS không có CĐKT → lấy từ PDF


# ── Parsers nguồn ────────────────────────────────────────────────────────────

def test_dnse_udf_and_vietstock_parsers():
    df = DNSEClient.parse_udf({"t": [1760054400, 1760140800], "o": [1, 2], "h": [1, 2], "l": [1, 2],
                               "c": [100.5, 101.0], "v": [10, 20]}, "FPT")
    assert list(df["close"]) == [100.5, 101.0] and set(df["source"]) == {"dnse"}
    vs = VietstockClient.parse_financeinfo(
        [[{"YearPeriod": 2024, "TermCode": "N"}, {"YearPeriod": 2023, "TermCode": "N"}],
         {"Kết quả kinh doanh": [{"Name": "Doanh thu thuần", "Value1": 10.0, "Value2": 8.0}]}])
    assert canonicalize(vs, "is").loc[20240, "revenue"] == 10.0


# ── Cảnh báo, bộ lọc, Excel, PDF theo mục, đa luồng ──────────────────────────

def test_alert_conditions_and_evaluate(fake_repo):
    from data.database import Database
    from services.watchlist_service import WatchlistService, check_condition
    assert check_condition("price_above", 100, 120, None, None) is True
    assert check_condition("rsi_below", 30, None, None, None) is None
    ws = WatchlistService(repo=fake_repo, db=Database(":memory:"))
    ws.add("FPT")
    ws.add_alert("FPT", "price_above", 1000)       # giá giả lập ~105.000đ → kích hoạt
    ws.add_alert("FPT", "price_below", 1)          # không kích hoạt
    hit = ws.evaluate()
    assert len(hit) == 1 and hit[0]["price"] > 1000
    assert ws.alerts(active_only=True)["condition"].tolist() == ["price_below"]


def test_screener_filters_and_rank():
    from services.screener_service import ScreenerService
    df = pd.DataFrame({"symbol": ["A", "B", "C"], "pe": [8, 25, -5], "roe": [20, 10, 30], "revenue_growth": [5, 30, None]})
    f = ScreenerService.apply_filters(df, [("pe", "<=", 15), ("roe", ">=", 15)])
    assert f["symbol"].tolist() == ["A", "C"]                # C: P/E âm vẫn ≤ 15 nhưng bị phạt khi xếp hạng
    ranked = ScreenerService.rank(df, {"pe": 1, "roe": 1})
    # A: P/E rẻ nhất (1.0) + ROE 2/3 → 83.3 · C: P/E âm bị coi 0 + ROE cao nhất → 50 · B → 41.7
    assert ranked["symbol"].tolist() == ["A", "C", "B"]
    assert ranked.set_index("symbol")["rank_score"].to_dict() == pytest.approx({"A": 83.3, "C": 50.0, "B": 41.7})


def test_excel_and_pdf_sections(fake_repo, tmp_path):
    import openpyxl
    from reports.excel_export import export_financials
    from reports.pdf_generator import PDFReportGenerator
    from services.stock_service import StockService
    svc = StockService("FPT", days=500, repository=fake_repo)
    wb = openpyxl.load_workbook(io.BytesIO(export_financials("FPT", svc.get_financials(), svc.financial_summary())))
    assert {"KQKD", "CDKT", "LCTT", "Chi_so", "Nguon_du_lieu"} <= set(wb.sheetnames)
    a = svc.full_analysis()
    gen = PDFReportGenerator()
    full = gen.generate(a, "full", output_path=str(tmp_path / "f.pdf"))
    part = gen.generate(a, "x", output_path=str(tmp_path / "p.pdf"), sections=["summary", "ratios"])
    from pypdf import PdfReader
    assert len(PdfReader(io.BytesIO(full)).pages) > len(PdfReader(io.BytesIO(part)).pages)
    text = "".join(p.extract_text() for p in PdfReader(io.BytesIO(part)).pages)
    assert "Chỉ số tài chính" in text and "Báo cáo tài chính nhiều năm" not in text


def test_database_is_thread_safe():
    from data.database import Database
    db = Database(":memory:")
    errors = []

    def work(i):
        try:
            for j in range(20):
                db.add_watch(f"S{i}{j}")
                db.get_watchlist()
        except Exception as exc:     # pragma: no cover
            errors.append(exc)

    ts = [threading.Thread(target=work, args=(i,)) for i in range(6)]
    [t.start() for t in ts]
    [t.join(30) for t in ts]
    assert not errors and len(db.get_watchlist()) == 120


def test_duplicate_source_columns_are_tolerated():
    df = vci_income()
    dup = pd.concat([df, df[["2025"]]], axis=1)          # tên cột "2025" xuất hiện 2 lần
    w = canonicalize(dup, "is")
    assert w.loc[20250, "revenue"] == pytest.approx(30_000e9 * 1.15 ** 5)


def test_one_failing_section_does_not_break_full_analysis(fake_repo, monkeypatch):
    from services.stock_service import StockService
    svc = StockService("FPT", days=400, repository=fake_repo)
    monkeypatch.setattr(svc, "get_peer_stats", lambda: (_ for _ in ()).throw(ValueError("boom")))
    a = svc.full_analysis()
    assert "peers" in a["errors"] and "boom" in a["errors"]["peers"]
    assert a["technical"]["available"] and a["financial_summary"]["ratios"] is not None


def test_vci_ratio_quarterly_columns_labelled_by_year_only():
    """Lỗi thật: bảng chỉ số VCI có 16 cột quý nhưng nhãn chỉ ghi năm → 'Length of values (16)...'."""
    cols = [str(y) for y in (2025, 2024, 2023, 2022) for _ in range(4)]      # "2025" ×4, "2024" ×4 ...
    raw = pd.DataFrame([["Số CP lưu hành", "Outstanding shares", "outstanding_share"] + [1.2e9] * 16,
                        ["P/E", "P/E", "pe"] + list(range(16))],
                       columns=["item", "item_en", "item_id"] + cols)
    w = canonicalize(raw, "ratio")
    assert list(w.index) == [20220, 20230, 20240, 20250]
    assert w.loc[20250, "shares_outstanding"] == 1.2e9
    r = DataRepository(vnstock_client=FakeVnstock(), dnse_client=FakeDNSE(), vietstock_client=FakeVietstock(),
                       pdf_financial_loader=lambda s, p: pd.DataFrame(), use_cache=False)
    r._vnstock.get_financial_statement = (lambda sym, st, period="year", source=None:
                                          raw if st == "ratio" else FakeVnstock().get_financial_statement(sym, st, period, source))
    assert not r.get_financials("FPT", "year")["data"].empty


def test_degenerate_period_labels_are_ignored_and_displayable():
    from components.ui import unique_columns
    raw = pd.DataFrame([["Số CP lưu hành", None, "outstanding_share"] + [1.2e9] * 16],
                       columns=["item", "item_en", "item_id"] + ["2018"] * 16)
    assert canonicalize(raw, "ratio").empty                       # không gán nhầm vào năm 2018
    shown = unique_columns(raw)
    assert not shown.columns.duplicated().any() and shown.shape == raw.shape
