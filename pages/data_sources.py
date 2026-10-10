"""Trang – Trạng thái nguồn dữ liệu, chiến lược ghép nguồn, nguồn gốc dữ liệu của từng mã, nhật ký cập nhật."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from components.ui import page_header, symbol_input
from config.settings import settings
from data.cache import cache
from data.database import Database
from services.stock_service import StockService, get_repo


def render():
    page_header("🛰️ Nguồn Dữ Liệu", "Kiểm tra từng nguồn, xem dữ liệu của mỗi mã đến từ đâu, nhật ký cập nhật tự động")

    st.markdown("#### Chiến lược kết hợp nguồn")
    st.markdown(f"""
| Loại dữ liệu | Thứ tự ưu tiên | Ghi chú |
|---|---|---|
| Giá {settings.DNSE_RECENT_DAYS} ngày gần nhất | **DNSE** → nguồn lịch sử | giá khớp gần nhất cũng lấy từ DNSE |
| Giá lịch sử (cũ hơn) | {' → '.join(settings.PRICE_HISTORY_SOURCES)} | tự điều chỉnh hệ số ở điểm nối nếu hai nguồn lệch (cổ tức / chia tách) |
| BCTC năm & quý | {' → '.join(settings.FINANCIAL_SOURCES)} | nguồn sau bù kỳ/chỉ tiêu nguồn trước thiếu |
| Tài liệu PDF | {' → '.join(settings.DOCUMENT_SOURCES)} → website DN | luôn có thể tải lên tay |
""")
    st.caption("Đổi thứ tự trong file .env: DNSE_RECENT_DAYS, PRICE_HISTORY_SOURCES, FINANCIAL_SOURCES, DOCUMENT_SOURCES.")

    if st.button("🩺 Kiểm tra kết nối các nguồn"):
        with st.spinner("Đang kiểm tra..."):
            status = get_repo().get_provider_status()
        rows = []
        for name in ("dnse", "vnstock", "vietstock"):
            s = status.get(name, {})
            rows.append({"Nguồn": name, "Sẵn sàng": s.get("available"), "Phiên bản": s.get("version", ""),
                         "Lỗi gần nhất": s.get("last_error", ""), "Ghi chú": s.get("note", s.get("base_url", ""))})
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    st.markdown("#### Nguồn gốc dữ liệu của một mã")
    symbol = symbol_input("src_symbol")
    if symbol and st.button("Xem nguồn gốc"):
        svc = StockService(symbol, days=1095)
        px = svc.get_price_df()
        st.markdown("**Giá (3 năm)**")
        st.dataframe(pd.DataFrame(px.attrs.get("provenance", [])), use_container_width=True, hide_index=True)
        k = px.attrs.get("stitch_factor")
        if k:
            st.info(f"Đã nhân giá đoạn cũ với hệ số {k:.4f} để nối liền với dữ liệu DNSE (hai nguồn lệch nhau ở các phiên trùng).")
        fin = svc.get_financials("year")
        st.markdown("**BCTC năm – nhật ký thử nguồn**")
        st.dataframe(pd.DataFrame(fin.get("attempts", [])), use_container_width=True, hide_index=True)

    st.markdown("#### Nhật ký cập nhật tự động")
    log = Database().get_update_log()
    if log.empty:
        st.caption("Chưa có lần chạy nào. Lên lịch: `python scripts/daily_update.py` (xem hướng dẫn trong README).")
    else:
        st.dataframe(log, use_container_width=True, hide_index=True)

    c1, c2 = st.columns(2)
    with c1:
        st.metric("Số mục trong bộ nhớ đệm", cache.stats().get("size", 0))
    with c2:
        if st.button("🧹 Xóa bộ nhớ đệm"):
            cache.clear_all()
            st.success("Đã xóa – lần xem tiếp theo sẽ tải lại từ nguồn.")
