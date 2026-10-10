"""
Cập nhật dữ liệu hằng ngày – chạy tự động bằng Task Scheduler (Windows) hoặc cron (macOS/Linux).

Việc làm mỗi lần chạy:
  1. Cập nhật giá (DNSE + lịch sử) cho các mã trong danh mục theo dõi, danh mục đầu tư và VN-Index
  2. Thu thập tin tức doanh nghiệp mới và lưu vào cơ sở dữ liệu (xem lại theo ngày trên trang Tin tức)
  3. Kiểm tra cảnh báo giá
  4. (Thứ Hai hoặc khi dùng --financials) làm mới BCTC năm + quý
  5. (--documents) dò tài liệu BCTN/BCTC mới
Kết quả ghi vào bảng update_log (xem trên trang "Nguồn dữ liệu").

Cách chạy:
    python scripts/daily_update.py                 # chạy mặc định
    python scripts/daily_update.py --financials --documents
    python scripts/daily_update.py --symbols FPT,HPG,VCB

Lên lịch trên Windows (chạy 16:30 hằng ngày, sau giờ đóng cửa):
    schtasks /Create /SC DAILY /ST 16:30 /TN "StockAnalyticsDaily" ^
      /TR "\"C:\\duong_dan\\.venv\\Scripts\\python.exe\" \"C:\\duong_dan\\GPM1\\scripts\\daily_update.py\""
Trên macOS/Linux (crontab -e):
    30 16 * * 1-5  cd /duong_dan/GPM1 && .venv/bin/python scripts/daily_update.py
"""
from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from data.database import Database  # noqa: E402
from services.company_news_service import CompanyNewsService  # noqa: E402
from services.document_service import DocumentService  # noqa: E402
from services.stock_service import get_repo  # noqa: E402
from services.watchlist_service import WatchlistService  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("daily_update")


def target_symbols(db: Database, extra: str = "") -> list:
    syms = set(s.strip().upper() for s in extra.split(",") if s.strip())
    wl = db.get_watchlist()
    if not wl.empty:
        syms |= set(wl["symbol"].str.upper())
    pf = db.get_portfolio("default")
    if not pf.empty:
        syms |= set(pf["symbol"].str.upper())
    return sorted(syms)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Cập nhật dữ liệu hằng ngày")
    ap.add_argument("--symbols", default="", help="Danh sách mã thêm, cách nhau dấu phẩy")
    ap.add_argument("--financials", action="store_true", help="Làm mới BCTC (mặc định chỉ thứ Hai)")
    ap.add_argument("--documents", action="store_true", help="Dò tài liệu BCTN/BCTC mới")
    args = ap.parse_args(argv)

    db, repo = Database(), get_repo()
    syms = target_symbols(db, args.symbols)
    log.info("Mã cần cập nhật: %s", ", ".join(syms) or "(trống – thêm mã vào Danh mục theo dõi)")
    ok, fail = 0, []

    for idx in ("VNINDEX", "VN30"):
        df = repo.get_price_history(idx, days=400, force_refresh=True)
        log.info("%s: %d phiên", idx, len(df))

    news = CompanyNewsService()
    do_fin = args.financials or datetime.now().weekday() == 0
    docs = DocumentService() if args.documents else None
    for s in syms:
        try:
            px = repo.get_price_history(s, days=400, force_refresh=True)
            n = news.get_company_news(s, force_refresh=True).get("summary", {}).get("total", 0)
            msg = f"{s}: {len(px)} phiên giá, {n} tin"
            if do_fin:
                for p in ("year", "quarter"):
                    f = repo.get_financials(s, period=p, years=10, force_refresh=True)
                    msg += f", BCTC {p}: {len(f['data'])} kỳ"
            if docs is not None:
                d = docs.discover(s, repo.get_company_info(s))
                msg += f", {len(d)} tài liệu"
            log.info(msg)
            ok += 1
        except Exception as exc:
            fail.append(f"{s}: {exc}")
            log.exception("Lỗi cập nhật %s", s)

    triggered = WatchlistService(repo=repo, db=db).evaluate()
    for t in triggered:
        log.warning("CẢNH BÁO %s – %s %s (giá %s)", t["symbol"], t["condition"], t["threshold"], t["price"])

    detail = f"{ok} mã thành công; lỗi: {'; '.join(fail) or 'không'}; cảnh báo kích hoạt: {len(triggered)}"
    db.log_update("daily_update", "ok" if not fail else "partial", detail)
    log.info(detail)
    return 0 if not fail else 1


if __name__ == "__main__":
    raise SystemExit(main())
