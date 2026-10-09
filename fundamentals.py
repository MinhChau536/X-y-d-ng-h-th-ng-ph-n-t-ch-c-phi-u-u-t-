"""
NGUỒN BCTC CHÍNH: dữ liệu Báo cáo tài chính năm của doanh nghiệp niêm yết HSX/HNX
- Kế thừa từ repo tham khảo vn-annual-report-miner (Trương Minh Quân, MIT License),
  vốn dựng trên bộ dữ liệu vnfinancialdata của TS. Ngô Phú Thanh (UEL).
- Ánh xạ tên chỉ tiêu theo ITEM_MAPPING của arminer (đa ngành: DN thường, ngân hàng, CTCK, bảo hiểm).
- Ưu tiên file parquet đi kèm (data/bctc); nếu thiếu thì tải qua thư viện vnfinancialdata.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd

DATA_DIR = Path(__file__).parent / "data" / "bctc"
SOURCE_NAME = "BCTC năm HSX/HNX – vnfinancialdata (Ngô Phú Thanh, UEL) qua repo vn-annual-report-miner"

# Thứ tự ưu tiên tên chỉ tiêu (mở rộng từ FinancialDataProvider.ITEM_MAPPING của arminer)
ITEM_MAPPING = {
    "revenue": ["Doanh số thuần", "Doanh thu thuần", "Tổng thu nhập hoạt động",
                "Doanh thu thuần về hoạt động kinh doanh", "Doanh thu hoạt động",
                "Doanh thu phí bảo hiểm thuần", "Thu nhập lãi thuần"],
    "npat": ["Lợi nhuận của Cổ đông của Công ty mẹ", "Cổ đông của Công ty mẹ",
             "Lợi nhuận sau thuế phân bổ cho chủ sở hữu", "Lợi nhuận sau thuế của chủ sở hữu, tập đoàn",
             "Lãi/(lỗ) thuần sau thuế", "Lợi nhuận sau thuế", "Lợi nhuận kế toán sau thuế",
             "Lợi nhuận sau thuế thu nhập doanh nghiệp"],
    "eps": ["Lãi cơ bản trên cổ phiếu", "Thu nhập thuần trên cổ phiếu phổ thông"],
    "total_assets": ["TỔNG TÀI SẢN", "TỔNG CỘNG TÀI SẢN", "TỔNG CỘNG NGUỒN VỐN"],
    "equity": ["VỐN CHỦ SỞ HỮU", "Vốn chủ sở hữu", "Vốn và các quỹ"],
    "liabilities": ["NỢ PHẢI TRẢ", "Tổng nợ phải trả"],
    "charter_capital": ["Cổ phiếu phổ thông", "Vốn điều lệ", "Vốn góp", "Vốn đầu tư của chủ sở hữu"],
}
STATEMENT = {"revenue": "income_statement", "npat": "income_statement", "eps": "income_statement"}


@lru_cache(maxsize=8)
def _load(statement: str, exchange: str) -> pd.DataFrame:
    f = DATA_DIR / statement / f"{exchange}.parquet"
    if f.exists():
        df = pd.read_parquet(f, columns=["ticker", "year", "item_name", "value"])
    else:  # dự phòng: tải trực tiếp qua thư viện gốc
        import vnfinancialdata as vnf
        df = vnf.load(exchange=exchange, statement=statement)[["ticker", "year", "item_name", "value"]]
    df["item_name"] = df["item_name"].astype(str).str.strip()
    return df


def _ticker_rows(ticker: str, statement: str) -> pd.DataFrame:
    for ex in ("HSX", "HNX"):
        df = _load(statement, ex)
        sub = df[df["ticker"] == ticker]
        if len(sub):
            return sub
    return pd.DataFrame(columns=["ticker", "year", "item_name", "value"])


def get_fundamentals(ticker: str, n_years: int = 6) -> pd.DataFrame:
    """Trả về bảng theo năm: revenue, npat (tỷ đồng), eps, bvps (đồng), roe, roa, net_margin (%), de (lần)."""
    ticker = ticker.upper()
    rows = {"income_statement": _ticker_rows(ticker, "income_statement"),
            "balance_sheet": _ticker_rows(ticker, "balance_sheet")}
    if rows["income_statement"].empty:
        return pd.DataFrame()

    years = sorted(rows["income_statement"]["year"].unique())[-(n_years + 1):]  # +1 năm để tính tăng trưởng/ bình quân
    out = []
    for y in years:
        rec = {"year": int(y)}
        for key, names in ITEM_MAPPING.items():
            src = rows[STATEMENT.get(key, "balance_sheet")]
            sub = src[src["year"] == y]
            val = np.nan
            for nm in names:
                v = sub.loc[sub["item_name"] == nm, "value"].dropna()
                v = v[v != 0]
                if len(v):
                    # cùng tên có thể xuất hiện ở nhiều cấp; lấy giá trị lớn nhất = dòng tổng
                    val = float(v.abs().max()) if key in ("total_assets", "equity", "liabilities") else float(v.iloc[0])
                    break
            rec[key] = val
        out.append(rec)

    f = pd.DataFrame(out).sort_values("year").reset_index(drop=True)
    notes = []
    # Kiểm tra chất lượng 1: năm bị sao chép y hệt năm trước (lỗi nguồn) -> loại bỏ
    dup = (f["revenue"] == f["revenue"].shift()) & (f["npat"] == f["npat"].shift())
    if dup.any():
        notes.append("Loại năm " + ", ".join(map(str, f.loc[dup, "year"])) + " do số liệu trùng y hệt năm trước (nghi lỗi nguồn).")
        f = f[~dup].reset_index(drop=True)
    # Kiểm tra chất lượng 2: EPS bất hợp lý (khớp nhầm dòng) -> tính lại
    bad = f["eps"].abs() > 1e6
    if bad.any():
        notes.append("EPS công bố bất thường ở năm " + ", ".join(map(str, f.loc[bad, "year"])) + ", đã tính lại = LNST/số CP.")
        f.loc[bad, "eps"] = np.nan
    eq_avg = f["equity"].rolling(2, min_periods=1).mean()
    ta_avg = f["total_assets"].rolling(2, min_periods=1).mean()
    f["roe"] = f["npat"] / eq_avg * 100
    f["roa"] = f["npat"] / ta_avg * 100
    f["net_margin"] = f["npat"] / f["revenue"] * 100
    f["de"] = f["liabilities"] / f["equity"]
    shares = f["charter_capital"] / 10_000  # mệnh giá 10.000đ/cp
    f["shares"] = shares
    f["bvps"] = f["equity"] / shares
    # EPS: ưu tiên số công bố; nếu thiếu thì tự tính
    f["eps"] = f["eps"].where(f["eps"].notna() & (f["eps"] != 0), f["npat"] / shares)
    f["revenue"] = f["revenue"] / 1e9
    f["npat"] = f["npat"] / 1e9
    f = f.tail(n_years).reset_index(drop=True)
    f.attrs["notes"] = notes
    return f


def add_market_multiples(fin: pd.DataFrame, px: pd.DataFrame, year_end: dict | None = None) -> pd.DataFrame:
    """P/E, P/B lịch sử = giá đóng cửa phiên cuối năm / EPS, BVPS của năm đó."""
    fin = fin.copy()
    if year_end:
        ye = pd.Series(year_end)
    else:
        px = px.copy()
        px["year"] = px["time"].dt.year
        ye = px.groupby("year")["close"].last()
    fin["price_ye"] = fin["year"].map(ye)
    # Giá đã điều chỉnh theo chia cổ tức/thưởng cổ phiếu -> quy EPS, BVPS mọi năm về số CP hiện tại
    # để giá và lợi nhuận/CP cùng một cơ sở (tránh P/E lịch sử bị thấp giả).
    sh = fin["shares"].dropna()
    sh_last = sh.iloc[-1] if len(sh) else np.nan
    fin["eps_adj"] = fin["npat"] * 1e9 / sh_last
    fin["bvps_adj"] = fin["equity"] / sh_last
    fin["pe"] = np.where(fin["eps_adj"] > 0, fin["price_ye"] / fin["eps_adj"], np.nan)
    fin["pb"] = np.where(fin["bvps_adj"] > 0, fin["price_ye"] / fin["bvps_adj"], np.nan)
    return fin


def available_tickers() -> list[str]:
    out = set()
    for ex in ("HSX", "HNX"):
        try:
            out |= set(_load("income_statement", ex)["ticker"].unique())
        except Exception:
            pass
    return sorted(out)
