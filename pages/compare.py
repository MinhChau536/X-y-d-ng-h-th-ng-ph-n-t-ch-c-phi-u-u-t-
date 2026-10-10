"""Trang – So sánh 2–5 cổ phiếu: chỉ số, định giá, diễn biến giá chuẩn hóa."""
from __future__ import annotations

import streamlit as st

from components.charts import line_comparison_chart
from components.ui import bar_chart, fmt_num, page_header
from services.screener_service import PROFILE_COLUMNS, compare


def render():
    page_header("⚖️ So Sánh Cổ Phiếu", "Đặt nhiều mã cạnh nhau: định giá, sinh lời, tăng trưởng, sức khỏe tài chính, hiệu suất giá")
    raw = st.text_input("Các mã cần so sánh (2–5 mã, cách nhau dấu phẩy)",
                        value=f"{st.session_state.get('current_symbol', 'FPT')},CMG,ELC")
    symbols = [s.strip().upper() for s in raw.split(",") if s.strip()][:5]
    if len(symbols) < 2:
        st.info("Nhập ít nhất 2 mã.")
        return
    if not st.button("So sánh", type="primary"):
        return
    with st.spinner("Đang tải dữ liệu..."):
        res = compare(symbols)
    table = res["table"]
    if table.empty:
        st.error("Không lấy được dữ liệu.")
        return
    show = table.set_index("symbol").drop(columns=["error"], errors="ignore")
    show = show.rename(columns=PROFILE_COLUMNS).T
    show = show.apply(lambda col: col.map(lambda v: fmt_num(v, 2) if isinstance(v, (int, float)) else (v if v is not None else "–")))
    st.dataframe(show, use_container_width=True)

    norm = res["normalized_prices"]
    if not norm.empty:
        st.plotly_chart(line_comparison_chart({c: norm[c] for c in norm.columns},
                                              "Diễn biến giá (gốc = 100)", pct_normalize=False),
                        use_container_width=True)
    c1, c2 = st.columns(2)
    syms = table["symbol"].tolist()
    with c1:
        st.plotly_chart(bar_chart(syms, {"ROE %": table.get("roe", []), "Biên LN ròng %": table.get("net_margin", [])},
                                  "Khả năng sinh lời", "%"), use_container_width=True)
    with c2:
        st.plotly_chart(bar_chart(syms, {"P/E": table.get("pe", []), "P/B": table.get("pb", [])}, "Định giá", "lần"),
                        use_container_width=True)
