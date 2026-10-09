"""Lấy báo cáo tài chính của cổ phiếu HSX/HNX từ gói `vnfinancialdata`.

Dùng như thư viện (để ghép với phần của các bạn):
    from fetch_financials import get_financials
    d = get_financials("VNM")            # d["balance_sheet"], d["income_statement"], d["cash_flow"]

Chạy trực tiếp:
    python fetch_financials.py            -> nhập mã tương tác ('thoát' để dừng)
    python fetch_financials.py VNM HPG    -> lấy nhiều mã, lưu vào thư mục output/

Mỗi bảng: dòng = chỉ tiêu (item_name), cột = năm. Giá trị giữ NGUYÊN như dataset (chưa đổi đơn vị).
Nguồn: gói vnfinancialdata (Ngo Phu Thanh, UEL), dataset v1.0.0 - chỉ có HSX/HNX, dữ liệu theo NĂM.
"""
from __future__ import annotations

import difflib
import re
import sys
import unicodedata
from functools import lru_cache
from pathlib import Path

import pandas as pd

EXCHANGES = ("HSX", "HNX")
STATEMENTS = {
    "balance_sheet": "Bảng cân đối kế toán",
    "income_statement": "Kết quả kinh doanh",
    "cash_flow": "Lưu chuyển tiền tệ",
}


class TickerNotFound(ValueError):
    pass


# ----------------------------------------------------------------------------- tải dữ liệu
def _load_raw(exchange: str, statement: str) -> pd.DataFrame:
    import vnfinancialdata as vnf          # import muộn để dễ test
    return vnf.load(exchange=exchange, statement=statement)


@lru_cache(maxsize=6)
def _load(exchange: str, statement: str) -> pd.DataFrame:
    try:
        df = _load_raw(exchange, statement)
    except Exception as exc:
        raise RuntimeError(
            f"Không tải được dữ liệu ({exchange}, {statement}): {exc}\n"
            "Kiểm tra: đã cài `pip install -U vnfinancialdata`, có Internet; "
            "nếu báo lỗi xác thực Hugging Face thì chạy `hf auth login`."
        ) from exc
    missing = {"ticker", "year", "item_name", "value"} - set(df.columns)
    if missing:
        raise RuntimeError(f"Schema dữ liệu đổi, thiếu cột {sorted(missing)}; cột hiện có: {list(df.columns)}")
    df = df.copy()
    df["ticker"] = df["ticker"].astype(str).str.upper().str.strip()
    df["year"] = pd.to_numeric(df["year"], errors="coerce")
    df["value"] = pd.to_numeric(df["value"], errors="coerce")
    return df.dropna(subset=["year"])


def _suggest(symbol: str, n: int = 5) -> list[str]:
    tickers = set()
    for ex in EXCHANGES:
        tickers |= set(_load(ex, "income_statement")["ticker"].unique())
    return difflib.get_close_matches(symbol, sorted(tickers), n=n, cutoff=0.5)


def _find_exchange(symbol: str) -> str:
    for ex in EXCHANGES:
        for st in ("income_statement", "balance_sheet"):
            if (_load(ex, st)["ticker"] == symbol).any():
                return ex
    hint = _suggest(symbol)
    raise TickerNotFound(
        f"Mã {symbol} không có trong dataset (chỉ có HSX/HNX, không có UPCoM)."
        + (f" Có phải bạn muốn: {', '.join(hint)}?" if hint else " Kiểm tra lại mã.")
    )


# ----------------------------------------------------------------------------- chuyển dạng bảng
def _norm(name) -> str:
    s = unicodedata.normalize("NFC", str(name))      # thống nhất dạng dấu tiếng Việt
    return re.sub(r"\s+", " ", s).strip()


def _to_wide(long: pd.DataFrame) -> pd.DataFrame:
    """long (ticker, year, item_name, value) -> dòng = chỉ tiêu, cột = năm. Thiếu dữ liệu = NaN (không phải 0)."""
    if long.empty:
        return pd.DataFrame()
    d = long[["item_name", "year", "value"]].copy()
    d["item_name"] = d["item_name"].map(_norm)
    d["year"] = d["year"].astype(int)
    order = d["item_name"].drop_duplicates()
    wide = d.groupby(["item_name", "year"], sort=False)["value"].first().unstack("year")
    wide = wide.reindex(order).reindex(columns=sorted(wide.columns)).astype(float)
    wide.index.name = "Chỉ tiêu"
    return wide


# ----------------------------------------------------------------------------- hàm chính
def get_financials(symbol: str, n_years: int | None = None, exchange: str | None = None) -> dict:
    """Trả về dict: symbol, exchange, balance_sheet, income_statement, cash_flow (DataFrame),
    years, long (dữ liệu dạng dài gồm item_code), meta."""
    symbol = symbol.upper().strip()
    ex = exchange or _find_exchange(symbol)
    out = {"symbol": symbol, "exchange": ex}
    longs = []
    for st in STATEMENTS:
        df = _load(ex, st)
        long = df[df["ticker"] == symbol]
        longs.append(long)
        wide = _to_wide(long)
        if n_years and not wide.empty:
            wide = wide[list(wide.columns)[-n_years:]]
        out[st] = wide
    if all(out[st].empty for st in STATEMENTS):
        raise TickerNotFound(f"Mã {symbol} không có dữ liệu trên {ex}.")
    out["years"] = sorted({int(y) for st in STATEMENTS for y in out[st].columns})
    out["long"] = pd.concat(longs, ignore_index=True)
    try:
        from importlib.metadata import version
        pkg = version("vnfinancialdata")
    except Exception:
        pkg = "không xác định"
    out["meta"] = {"nguồn": "vnfinancialdata (Ngo Phu Thanh, UEL)", "phiên bản gói": pkg,
                   "dataset": "v1.0.0", "schema": "1.0", "tần suất": "năm",
                   "đơn vị": "giữ nguyên như dataset — cần tự kiểm tra"}
    return out


def save_excel(data: dict, out_dir: str = "output", extra: dict | None = None) -> str:
    """extra: {tên sheet: (DataFrame, tập tên dòng hiển thị dạng %)} - ghi thêm sheet (vd. chỉ số tài chính)."""
    path = Path(out_dir) / f"{data['symbol']}_financials.xlsx"
    path.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(path, engine="openpyxl") as xw:
        info = pd.DataFrame({"Thông tin": ["Mã", "Sàn", "Năm dữ liệu", *data["meta"].keys()],
                             "Giá trị": [data["symbol"], data["exchange"],
                                         f"{data['years'][0]}–{data['years'][-1]}", *data["meta"].values()]})
        info.to_excel(xw, sheet_name="Thông tin", index=False)
        for st, label in STATEMENTS.items():
            if not data[st].empty:
                data[st].to_excel(xw, sheet_name=label)
        for name, (df, pct) in (extra or {}).items():
            df.to_excel(xw, sheet_name=name)
        for ws in xw.sheets.values():
            ws.column_dimensions["A"].width = 60
            for col in "BCDEFGHIJKLMN":
                ws.column_dimensions[col].width = 18
            ws.freeze_panes = "B2"
        for st, label in STATEMENTS.items():       # định dạng số có dấu phân cách nghìn
            if label in xw.sheets:
                for row in xw.sheets[label].iter_rows(min_row=2, min_col=2):
                    for c in row:
                        c.number_format = "#,##0.00"
        for name, (df, pct) in (extra or {}).items():
            for row in xw.sheets[name].iter_rows(min_row=2, min_col=2):
                fmt = "0.0%" if row[0].offset(column=-1).value in pct else "#,##0.00"
                for c in row:
                    c.number_format = fmt
    for st in STATEMENTS:
        if not data[st].empty:
            data[st].to_csv(path.with_name(f"{data['symbol']}_{st}.csv"), encoding="utf-8-sig")
    return str(path)


def show(data: dict, last_n: int = 5) -> None:
    print(f"\n=== {data['symbol']} ({data['exchange']}) – năm {data['years'][0]} đến {data['years'][-1]} ===")
    for st, label in STATEMENTS.items():
        w = data[st]
        if w.empty:
            print(f"\n-- {label}: KHÔNG CÓ DỮ LIỆU --")
            continue
        print(f"\n-- {label}: {len(w)} chỉ tiêu (hiện {last_n} năm gần nhất, 20 dòng đầu) --")
        print(w.iloc[:, -last_n:].head(20).to_string(float_format=lambda v: f"{v:,.0f}"))


# ----------------------------------------------------------------------------- chạy dòng lệnh
def _run_one(sym: str, out_dir: str, n_years: int | None, n_show: int = 5) -> bool:
    try:
        d = get_financials(sym, n_years)
    except TickerNotFound as e:
        print(f"[!] {e}")
        return False
    except Exception as e:
        print(f"[!] Không xử lý được {sym}: {type(e).__name__}: {e}")
        return False
    show(d)
    extra = None
    try:
        from ratios import PERCENT, get_ratios
        rr = get_ratios(d)
        extra = {"Chỉ số tài chính": (rr["ratios"].T, PERCENT), "Ánh xạ biến": (rr["mapping"].set_index("Khái niệm"), set())}
        print(f"\n-- Chỉ số tài chính ({rr['sector_label']}, {n_show} năm gần nhất) --")
        print(rr["ratios"].tail(n_show).T.dropna(how="all").to_string(
            float_format=lambda v: f"{v:,.3f}"))
    except Exception as e:                      # lỗi phần chỉ số không được làm mất dữ liệu BCTC
        print(f"[!] Không tính được chỉ số tài chính: {type(e).__name__}: {e}")
    print("\nĐã lưu:", save_excel(d, out_dir, extra))
    return True


def main(argv: list[str]) -> int:
    out_dir = "output"
    syms = [a for a in argv if not a.startswith("--")]
    if syms:
        return 0 if all([_run_one(s, out_dir, None) for s in syms]) else 1
    print("Nhập mã cổ phiếu (vd VNM, HPG, VCB). Gõ 'thoát' để dừng.")
    while True:
        try:
            sym = input("\nMã > ").strip().upper()
        except (EOFError, KeyboardInterrupt):
            return 0
        if sym in ("THOÁT", "THOAT", "EXIT", "Q"):
            return 0
        if sym:
            _run_one(sym, out_dir, None)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
