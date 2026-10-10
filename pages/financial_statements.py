"""
Trang – Báo cáo tài chính nhiều năm (chuẩn hóa từ nhiều nguồn) + tải Excel.
"""
from __future__ import annotations

from datetime import datetime

import pandas as pd
import streamlit as st

from analytics.period_utils import key_to_label
from components.ui import bar_chart, fmt_num, page_header, source_caption, symbol_input, unique_columns
from data.financial_mapping import ITEMS_BY_KEY, PER_UNIT_KEYS, STATEMENT_ITEMS
from reports.excel_export import export_financials, statement_table
from services.stock_service import StockService

_TABS = [("is", "📊 Kết quả kinh doanh"), ("bs", "🏦 Cân đối kế toán"), ("cf", "💸 Lưu chuyển tiền tệ")]


def _display_table(data: pd.DataFrame, sources: pd.DataFrame, st_code: str) -> pd.DataFrame:
    t = statement_table(data, st_code, unit=1e9)
    if t.empty:
        return t
    t = t.set_index("Chỉ tiêu")
    return t.apply(lambda col: col.map(lambda v: fmt_num(v, 0)))


def render():
    page_header("📑 Báo Cáo Tài Chính Nhiều Năm",
                "Kết hợp nhiều nguồn (vnstock VCI → KBS → Vietstock → PDF BCTC) – nguồn sau tự bù phần nguồn trước thiếu")

    c1, c2, c3, c4 = st.columns([2, 1, 1, 1])
    with c1:
        symbol = symbol_input("fs_symbol")
    with c2:
        period = st.selectbox("Kỳ báo cáo", ["year", "quarter"], format_func=lambda p: "Năm" if p == "year" else "Quý")
    with c3:
        years = st.slider("Số năm", 3, 15, 8)
    with c4:
        st.write("")
        refresh = st.button("🔄 Làm mới", help="Bỏ qua bộ nhớ đệm, tải lại từ các nguồn")
    if not symbol:
        return

    with st.spinner(f"Đang tổng hợp BCTC {symbol} từ các nguồn..."):
        svc = StockService(symbol, fin_period=period, fin_years=years)
        if refresh:
            svc.repo.get_financials(symbol, period=period, years=years, force_refresh=True)
        fin = svc.get_financials(period, years)
    data, sources = fin.get("data", pd.DataFrame()), fin.get("sources", pd.DataFrame())

    if data is None or data.empty:
        st.error("Không lấy được BCTC từ nguồn nào. Xem chi tiết từng nguồn ở trang 🛰️ Nguồn dữ liệu, "
                 "hoặc tải BCTC dạng PDF ở trang 📚 Tài liệu để hệ thống tự trích số liệu.")
        with st.expander("Nhật ký thử nguồn"):
            st.dataframe(pd.DataFrame(fin.get("attempts", [])), use_container_width=True)
        return

    used = sorted({str(x) for x in pd.unique(sources.values.ravel()) if isinstance(x, str)}) if not sources.empty else []
    source_caption(f"{len(data)} kỳ ({key_to_label(data.index[0])} → {key_to_label(data.index[-1])}) · nguồn: "
                   f"{', '.join(used) or 'bộ nhớ DuckDB'} · đơn vị: tỷ đồng (EPS: đồng/cp)")

    # Biểu đồ nhanh
    periods = [key_to_label(k) for k in data.index]
    g1, g2 = st.columns(2)
    with g1:
        series = {}
        for k, name in (("revenue", "Doanh thu thuần"), ("total_operating_income", "Tổng thu nhập HĐ"),
                        ("net_income_parent", "LNST cổ đông mẹ"), ("net_income", "LNST")):
            if k in data.columns and data[k].notna().any() and len(series) < 2:
                series[name] = (data[k] / 1e9).tolist()
        st.plotly_chart(bar_chart(periods, series, "Doanh thu & Lợi nhuận", "tỷ đồng"), use_container_width=True)
    with g2:
        series = {}
        for k, name in (("total_assets", "Tổng tài sản"), ("equity", "Vốn chủ sở hữu"), ("total_liabilities", "Nợ phải trả")):
            if k in data.columns and data[k].notna().any():
                series[name] = (data[k] / 1e9).tolist()
        st.plotly_chart(bar_chart(periods, series, "Cơ cấu tài sản – nguồn vốn", "tỷ đồng"), use_container_width=True)

    tabs = st.tabs([t[1] for t in _TABS] + ["🧾 Bảng gốc từng nguồn", "🛰️ Nguồn từng ô"])
    for (code, _), tab in zip(_TABS, tabs[:3]):
        with tab:
            t = _display_table(data, sources, code)
            if t.empty:
                st.info("Không có số liệu cho báo cáo này.")
            else:
                st.dataframe(t, use_container_width=True, height=min(700, 38 + 35 * len(t)))
    with tabs[3]:
        raw = fin.get("raw") or {}
        if not raw:
            st.info("Không có bảng gốc (dữ liệu lấy từ bộ nhớ đệm DuckDB hoặc PDF).")
        for stmt, by_src in raw.items():
            for src, df in by_src.items():
                with st.expander(f"{stmt} – {src} ({len(df)} dòng)"):
                    if df.columns.duplicated().any():
                        st.caption("⚠️ Nguồn trả về nhiều cột kỳ trùng nhãn – các cột đã được đánh số để hiển thị.")
                    st.dataframe(unique_columns(df), use_container_width=True)
    with tabs[4]:
        if not sources.empty:
            s = sources.copy()
            s.index = [key_to_label(k) for k in s.index]
            s.columns = [ITEMS_BY_KEY[c].label_vi if c in ITEMS_BY_KEY else c for c in s.columns]
            st.dataframe(s.T.fillna("–"), use_container_width=True)
        with st.expander("Nhật ký thử từng nguồn"):
            st.dataframe(pd.DataFrame(fin.get("attempts", [])), use_container_width=True)

    st.download_button(
        "⬇️ Tải Excel (BCTC + Chỉ số + Nguồn + Bảng gốc)",
        data=export_financials(symbol, fin, svc.financial_summary(period)),
        file_name=f"{symbol}_BCTC_{'nam' if period == 'year' else 'quy'}_{datetime.now():%Y%m%d}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        type="primary",
    )
