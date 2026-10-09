"""
Chạy từ dòng lệnh:
    python main.py FPT              -> output/FPT_report.pdf (dữ liệu thật qua vnstock)
    python main.py FPT HPG VCB      -> nhiều mã cùng lúc
    python main.py FPT --demo       -> dữ liệu mô phỏng (khi API lỗi)
"""
import argparse
import datetime as dt

from analyzer import load_data, analyze
from report import build_pdf


def run(ticker: str, demo: bool = False) -> str:
    data = load_data(ticker, demo=demo)
    a = analyze(data)
    out = f"output/{data['ticker']}_{dt.date.today():%Y%m%d}.pdf"
    build_pdf(data, a, out)
    print(f"[OK] {data['ticker']}: {a['rec']} | điểm {a['total']:.0f}/100 | "
          f"giá {a['price']:,.0f} | mục tiêu {a['target'] or 0:,.0f} -> {out}")
    return out


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Hệ thống phân tích cơ hội đầu tư cổ phiếu")
    p.add_argument("tickers", nargs="+", help="Mã cổ phiếu, vd FPT HPG VCB")
    p.add_argument("--demo", action="store_true", help="Dùng dữ liệu mô phỏng")
    args = p.parse_args()
    for t in args.tickers:
        try:
            run(t, args.demo)
        except Exception as e:
            print(f"[LỖI] {t}: {e}")
