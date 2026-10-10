"""
Chẩn đoán lỗi từng bước với dữ liệu THẬT.
Chạy:  python debug_fpt.py FPT
Kết quả in ra màn hình và lưu vào file debug_FPT.txt – gửi file này để sửa lỗi.
"""
import io
import sys
import traceback
from contextlib import redirect_stdout

import pandas as pd

pd.set_option("display.width", 250)
pd.set_option("display.max_columns", 30)
SYM = (sys.argv[1] if len(sys.argv) > 1 else "FPT").upper()
buf = io.StringIO()


def step(name, fn):
    print(f"\n{'=' * 20} {name} {'=' * 20}")
    try:
        res = fn()
        print("OK")
        return res
    except Exception:
        traceback.print_exc(file=sys.stdout)
        return None


def show(df, label):
    if df is None:
        print(f"[{label}] None"); return
    if isinstance(df, pd.DataFrame):
        print(f"[{label}] shape={df.shape}")
        print("  columns:", list(df.columns)[:40])
        print("  duplicated columns:", list(df.columns[df.columns.duplicated()]))
        print(df.head(6).to_string()[:3000])
    else:
        print(f"[{label}] {type(df)}: {str(df)[:1500]}")


with redirect_stdout(buf):
    import vnstock
    print("vnstock", getattr(vnstock, "__version__", "?"), "| pandas", pd.__version__, "| python", sys.version)
    from data.providers.vnstock_client import VnstockClient
    from data.providers.dnse_client import DNSEClient
    from data.financial_mapping import canonicalize
    vc, dc = VnstockClient(), DNSEClient()

    step("DNSE giá", lambda: show(dc.get_price_history(SYM, "2026-09-01", "2026-10-09"), "dnse"))
    step("vnstock giá VCI", lambda: show(vc.get_price_history(SYM, "2024-01-01", "2024-02-01", source="vci"), "vci price"))
    step("Hồ sơ công ty", lambda: print(vc.get_company_info(SYM)))
    for src in ("vci", "kbs"):
        for stmt, code in (("income_statement", "is"), ("balance_sheet", "bs"), ("cash_flow", "cf"), ("ratio", "ratio")):
            raw = step(f"{src} {stmt} (năm) – bảng gốc", lambda: vc.get_financial_statement(SYM, stmt, "year", source=src))
            show(raw, f"{src}/{stmt}")
            if raw is not None and not raw.empty:
                step(f"{src} {stmt} – chuẩn hóa", lambda: show(canonicalize(raw, code), "canonical"))

    from services.stock_service import StockService
    svc = StockService(SYM)
    step("Repository.get_financials(year)", lambda: show(svc.get_financials("year")["data"], "fin year"))
    step("technical_analysis", lambda: svc.technical_analysis()["available"])
    step("fundamental_analysis", lambda: svc.fundamental_analysis()["score"])
    step("momentum_analysis", lambda: svc.momentum_analysis()["score"]["score"])
    step("get_peer_stats", lambda: print(svc.get_peer_stats()))
    step("valuation_analysis", lambda: svc.valuation_analysis()["score"]["score"])
    step("financial_summary", lambda: print(svc.financial_summary()["valuation"]))
    step("full_analysis", lambda: svc.full_analysis() and None)

out = buf.getvalue()
print(out)
with open(f"debug_{SYM}.txt", "w", encoding="utf-8") as f:
    f.write(out)
print(f"\n>>> Đã lưu debug_{SYM}.txt – gửi file này cho Claude.")
