import pandas as pd, pytest
import fetch_financials as f

Y = [2023, 2024, 2025]
COLS = ["ticker", "year", "item_code", "item_name", "value"]
def long(t, st, items):
    return pd.DataFrame(columns=COLS) if not items else pd.DataFrame([dict(ticker=t, year=y, item_code=f"{st[:2]}{i}", item_name=n, value=v)
                         for i, (n, vs) in enumerate(items.items()) for y, v in zip(Y, vs)])

@pytest.fixture(autouse=True)
def fake(monkeypatch):
    st = {"balance_sheet": long("TST", "balance_sheet", {"TỔNG TÀI SẢN": [1e12, 1.1e12, 1.2e12], "Tiền  và tương đương tiền": [1, None, 3]}),
          "income_statement": long("TST", "income_statement", {"Doanh số thuần": [5, 6, 7]}),
          "cash_flow": long("TST", "cash_flow", {})}
    empty = pd.DataFrame(columns=["ticker", "year", "item_name", "value"])
    monkeypatch.setattr(f, "_load_raw", lambda ex, s: st[s] if ex == "HSX" else empty)
    f._load.cache_clear(); yield; f._load.cache_clear()

def test_wide_and_missing_not_zero():
    d = f.get_financials("tst")
    bs = d["balance_sheet"]
    assert list(bs.columns) == Y and bs.loc["TỔNG TÀI SẢN", 2025] == 1.2e12
    assert pd.isna(bs.loc["Tiền và tương đương tiền", 2024])      # khoảng trắng thừa được chuẩn hóa, thiếu = NaN
    assert d["cash_flow"].empty and d["years"] == Y and d["exchange"] == "HSX"

def test_n_years_and_unknown():
    assert list(f.get_financials("TST", n_years=2)["income_statement"].columns) == [2024, 2025]
    with pytest.raises(f.TickerNotFound, match="TST"):
        f.get_financials("TTS")

def test_save_excel(tmp_path):
    p = f.save_excel(f.get_financials("TST"), str(tmp_path))
    assert {"Thông tin", "Bảng cân đối kế toán", "Kết quả kinh doanh"} <= set(pd.ExcelFile(p).sheet_names)
