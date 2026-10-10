"""
Nguồn dữ liệu GIẢ LẬP cho kiểm thử (không gọi mạng).

Định dạng bám theo dữ liệu thật của vnstock 4.x (docs/SCHEMA_SNAPSHOT.md):
  - BCTC VCI: ma trận item / item_en / item_id × kỳ, kỳ MỚI NHẤT ĐỨNG TRƯỚC, có cột trùng "_1"
  - BCTC KBS: cùng dạng nhưng item_id đã chuẩn hóa và chỉ có 4 kỳ gần nhất
  - Giá VCI/DNSE: theo nghìn đồng (vd 105.5)
"""
from __future__ import annotations

from typing import Dict, List, Optional

import numpy as np
import pandas as pd

YEARS = [2025, 2024, 2023, 2022, 2021, 2020]       # mới nhất trước, như VCI


def _annual(base: float, growth: float) -> Dict[int, float]:
    return {y: base * (1 + growth) ** (y - 2020) for y in YEARS}


REV = _annual(30_000e9, 0.15)
NI = {y: v * 0.13 for y, v in REV.items()}
TA = _annual(40_000e9, 0.12)
EQ = {y: v * 0.45 for y, v in TA.items()}


def vci_income(years=YEARS, quarterly=False) -> pd.DataFrame:
    cols = [f"{y}-Q{q}" for y in years for q in (4, 3, 2, 1)] if quarterly else [str(y) for y in years]
    def val(series, c):
        y = int(c[:4])
        return series[y] / 4 if quarterly else series[y]
    rows = [
        ("Tăng trưởng doanh thu (%)", "Revenue growth", "revenue_yoy", [15.0] * len(cols)),
        ("Doanh thu bán hàng và cung cấp dịch vụ", "Sales", "sales", [val(REV, c) * 1.01 for c in cols]),
        ("Các khoản giảm trừ doanh thu", "Deductions", "deduct", [-val(REV, c) * 0.01 for c in cols]),
        ("Doanh thu thuần", "Net revenue", "net_revenue_x", [val(REV, c) for c in cols]),
        ("Giá vốn hàng bán", "COGS", "cogs_x", [-val(REV, c) * 0.62 for c in cols]),
        ("Lợi nhuận gộp", "Gross profit", "gp_x", [val(REV, c) * 0.38 for c in cols]),
        ("Chi phí tài chính", "Financial expenses", "fe", [-val(REV, c) * 0.02 for c in cols]),
        ("Trong đó: Chi phí lãi vay", "Interest expenses", "ie", [-val(REV, c) * 0.012 for c in cols]),
        ("Lợi nhuận thuần từ hoạt động kinh doanh", "Operating profit", "op", [val(REV, c) * 0.165 for c in cols]),
        ("Tổng lợi nhuận kế toán trước thuế", "Profit before tax", "pbt", [val(NI, c) / 0.8 for c in cols]),
        ("Chi phí thuế TNDN hiện hành", "Current income tax", "tax", [-val(NI, c) / 0.8 * 0.2 for c in cols]),
        ("Lợi nhuận sau thuế thu nhập doanh nghiệp", "Net profit after tax", "npat", [val(NI, c) for c in cols]),
        ("Lợi nhuận sau thuế của cổ đông công ty mẹ", "Attributable to parent", "npat_parent", [val(NI, c) * 0.92 for c in cols]),
        ("Lãi cơ bản trên cổ phiếu", "Basic EPS", "eps_x", [val(NI, c) * 0.92 / 1.2e9 for c in cols]),
    ]
    df = pd.DataFrame([{"item": a, "item_en": b, "item_id": c, **dict(zip(cols, v))} for a, b, c, v in rows])
    df[f"{cols[0]}_1"] = 0.0     # cột trùng như dữ liệu thật
    return df


def vci_balance(years=YEARS) -> pd.DataFrame:
    cols = [str(y) for y in years]
    rows = [
        ("TÀI SẢN NGẮN HẠN", "current_assets_x", [TA[y] * 0.55 for y in years]),
        ("Tiền và các khoản tương đương tiền", "cash_x", [TA[y] * 0.10 for y in years]),
        ("Đầu tư tài chính ngắn hạn", "sti", [TA[y] * 0.12 for y in years]),
        ("Các khoản phải thu ngắn hạn", "recv", [TA[y] * 0.18 for y in years]),
        ("Hàng tồn kho", "inv", [TA[y] * 0.10 for y in years]),
        ("Tài sản cố định", "fa", [TA[y] * 0.25 for y in years]),
        ("TỔNG CỘNG TÀI SẢN", "ta", [TA[y] for y in years]),
        ("NỢ PHẢI TRẢ", "tl", [TA[y] - EQ[y] for y in years]),
        ("Nợ ngắn hạn", "cl", [TA[y] * 0.40 for y in years]),
        ("Phải trả người bán ngắn hạn", "ap", [TA[y] * 0.08 for y in years]),
        ("Vay và nợ thuê tài chính ngắn hạn", "std", [TA[y] * 0.15 for y in years]),
        ("Nợ dài hạn", "ltl", [TA[y] * 0.15 for y in years]),
        ("Vay và nợ thuê tài chính dài hạn", "ltd", [TA[y] * 0.08 for y in years]),
        ("VỐN CHỦ SỞ HỮU", "eq", [EQ[y] for y in years]),
        ("Vốn góp của chủ sở hữu", "cap", [12_000e9 for _ in years]),
        ("Lợi nhuận sau thuế chưa phân phối", "re", [EQ[y] * 0.35 for y in years]),
        ("Lợi ích cổ đông không kiểm soát", "mi", [EQ[y] * 0.08 for y in years]),
    ]
    return pd.DataFrame([{"item": a, "item_en": None, "item_id": c, **dict(zip(cols, v))} for a, c, v in rows])


def vci_cashflow(years=YEARS) -> pd.DataFrame:
    cols = [str(y) for y in years]
    rows = [
        ("Khấu hao TSCĐ", "dep", [REV[y] * 0.04 for y in years]),
        ("Lưu chuyển tiền thuần từ hoạt động kinh doanh", "cfo", [NI[y] * 1.15 for y in years]),
        ("Tiền chi để mua sắm, xây dựng TSCĐ và các tài sản dài hạn khác", "capex", [-REV[y] * 0.06 for y in years]),
        ("Lưu chuyển tiền thuần từ hoạt động đầu tư", "cfi", [-REV[y] * 0.07 for y in years]),
        ("Cổ tức, lợi nhuận đã trả cho chủ sở hữu", "div", [-NI[y] * 0.4 for y in years]),
        ("Lưu chuyển tiền thuần từ hoạt động tài chính", "cff", [-NI[y] * 0.5 for y in years]),
    ]
    return pd.DataFrame([{"item": a, "item_en": None, "item_id": c, **dict(zip(cols, v))} for a, c, v in rows])


def vci_ratio() -> pd.DataFrame:
    cols = ["2025-Q4", "2025-Q3", "2025-Q2", "2025-Q1"]
    return pd.DataFrame([
        {"item": "P/E", "item_en": "P/E", "item_id": "pe", **{c: 19.0 for c in cols}},
        {"item": "P/B", "item_en": "P/B", "item_id": "pb", **{c: 4.5 for c in cols}},
        {"item": "ROE (%)", "item_en": "ROE", "item_id": "roe", **{c: 0.27 for c in cols}},
        {"item": "Số CP lưu hành", "item_en": "Outstanding shares", "item_id": "outstanding_share", **{c: 1.2e9 for c in cols}},
    ])


def kbs_income() -> pd.DataFrame:
    yrs = YEARS[:4]
    return pd.DataFrame([
        {"item": "Doanh thu thuần", "item_id": "revenue", **{str(y): REV[y] for y in yrs}},
        {"item": "Lợi nhuận sau thuế", "item_id": "net_profit", **{str(y): NI[y] for y in yrs}},
        {"item": "Chi phí bán hàng", "item_id": "selling_expenses", **{str(y): REV[y] * 0.05 for y in yrs}},
    ])


def price_frame(start: str, end: str, base: float = 100.0, drift: float = 0.0005, seed: int = 1,
                source: str = "x") -> pd.DataFrame:
    d = pd.bdate_range(start, end)
    rng = np.random.default_rng(seed)
    close = base * np.exp(np.cumsum(rng.normal(drift, 0.012, len(d))))
    return pd.DataFrame({"timestamp": d, "open": close * 0.998, "high": close * 1.01, "low": close * 0.99,
                         "close": close, "volume": rng.integers(5e5, 3e6, len(d)), "source": source})


class FakeVnstock:
    """Giả lập VnstockClient: VCI đủ 6 năm, KBS 4 năm, MSN không có BCTC."""

    def __init__(self, fail_vci_fin: bool = False, fail_price: bool = False):
        self.fail_vci_fin = fail_vci_fin
        self.fail_price = fail_price
        self.calls: List[tuple] = []

    def get_price_history(self, symbol, start, end, interval="1D", source=None):
        self.calls.append(("price", symbol, source))
        if self.fail_price:
            return pd.DataFrame()
        base = 1200.0 if symbol in ("VNINDEX", "VN30") else 100.0
        df = price_frame(start, end, base=base, seed=hash(symbol) % 100, source=f"vnstock_{(source or 'vci').replace('vnstock_', '')}")
        df["symbol"] = symbol
        return df

    def get_current_price(self, symbol):
        return None

    def get_financial_statement(self, symbol, statement, period="year", source=None):
        src = (source or "vci").replace("vnstock_", "")
        self.calls.append(("fin", statement, src, period))
        if src == "vci":
            if self.fail_vci_fin:
                return pd.DataFrame()
            return {"income_statement": vci_income(quarterly=(period == "quarter")),
                    "balance_sheet": vci_balance(), "cash_flow": vci_cashflow(), "ratio": vci_ratio()}[statement]
        if src == "kbs" and statement == "income_statement":
            return kbs_income()
        return pd.DataFrame()

    def get_financial_ratios(self, symbol, period="quarter"):
        return vci_ratio()

    def get_company_info(self, symbol):
        return {"symbol": symbol, "company_name": f"Công ty {symbol} (giả lập)", "exchange": "HOSE",
                "industry": "Công nghệ", "website": "https://example.com"}

    def get_company_news(self, symbol):
        return [{"title": f"{symbol} công bố kết quả kinh doanh tăng trưởng", "url": f"https://news.example/{symbol}/1",
                 "published_at": pd.Timestamp.now() - pd.Timedelta(days=1), "source": "vnstock_vci", "summary": ""}]

    def get_company_events(self, symbol):
        return pd.DataFrame()

    def get_shareholders(self, symbol):
        return pd.DataFrame()

    def get_officers(self, symbol):
        return pd.DataFrame()

    def get_all_symbols(self):
        return pd.DataFrame({"symbol": ["FPT", "CMG", "HPG"], "organ_name": ["FPT", "CMC", "Hòa Phát"]})

    def get_symbols_by_industries(self):
        return pd.DataFrame()

    def get_price_board(self, symbols):
        return pd.DataFrame()

    def health_check(self):
        return {"provider": "fake-vnstock", "available": True}


class FakeDNSE:
    def __init__(self, fail: bool = False, scale: float = 1.0):
        self.fail = fail
        self.scale = scale

    def get_price_history(self, symbol, start, end, interval="1D"):
        if self.fail:
            return pd.DataFrame()
        base = 1200.0 if symbol in ("VNINDEX", "VN30") else 100.0
        df = price_frame(start, end, base=base * self.scale, seed=7, source="dnse")
        df["symbol"] = symbol
        return df

    def get_current_price(self, symbol):
        if self.fail:
            return None
        return {"symbol": symbol, "price": 105.0, "source": "dnse", "timestamp": str(pd.Timestamp.now())}

    def health_check(self):
        return {"provider": "fake-dnse", "available": not self.fail}


class FakeVietstock:
    def __init__(self, has_data: bool = False):
        self.has_data = has_data

    def get_price_history(self, symbol, start, end, interval="1D"):
        if not self.has_data:
            return pd.DataFrame()
        return price_frame(start, end, base=100_000.0, seed=3, source="vietstock")

    def get_current_price(self, symbol):
        return None

    def get_financial_statement(self, symbol, statement, period="year", n_periods=8):
        if not self.has_data or statement != "cash_flow":
            return pd.DataFrame()
        # Vietstock bù thêm năm 2019 mà VCI không có
        return pd.DataFrame([{"item": "Lưu chuyển tiền thuần từ hoạt động kinh doanh", "2019": 3_000e9}])

    def health_check(self):
        return {"provider": "fake-vietstock"}
