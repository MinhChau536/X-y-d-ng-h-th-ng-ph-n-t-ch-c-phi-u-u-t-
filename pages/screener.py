"""
Trang – Bộ lọc cổ phiếu theo chỉ số tính từ BCTC & giá, kèm xếp hạng tổng hợp.
"""
from __future__ import annotations

from datetime import datetime

import pandas as pd
import streamlit as st

from components.ui import page_header
from data.database import Database
from data.ticker_directory import BASKETS, get_basket_names
from services.screener_service import PRESETS, PROFILE_COLUMNS, ScreenerService

_FILTERABLE = {
    "pe": ("P/E ≤", "<=", 0.0, 60.0, 15.0), "pb": ("P/B ≤", "<=", 0.0, 10.0, 2.0),
    "roe": ("ROE % ≥", ">=", -20.0, 50.0, 15.0), "net_margin": ("Biên LN ròng % ≥", ">=", -20.0, 60.0, 8.0),
    "revenue_growth": ("Tăng trưởng DT % ≥", ">=", -50.0, 100.0, 10.0),
    "net_income_growth": ("Tăng trưởng LNST % ≥", ">=", -50.0, 150.0, 10.0),
    "debt_to_equity": ("Nợ vay/VCSH ≤", "<=", 0.0, 5.0, 1.0), "dividend_yield": ("Tỷ suất cổ tức % ≥", ">=", 0.0, 15.0, 3.0),
    "fscore": ("F-score ≥", ">=", 0.0, 9.0, 6.0), "change_3m": ("% 3 tháng ≥", ">=", -50.0, 100.0, 0.0),
}


def render():
    page_header("🔎 Bộ Lọc Cổ Phiếu", "Lọc & xếp hạng theo chỉ số tính từ BCTC năm gần nhất và diễn biến giá")
    c1, c2 = st.columns([2, 2])
    with c1:
        universes = [b for b in get_basket_names() if "Tất cả" not in b] + ["⭐ Danh mục theo dõi", "✍️ Tự nhập"]
        uni = st.selectbox("Phạm vi cổ phiếu", universes)
    with c2:
        preset = st.selectbox("Bộ lọc mẫu", ["(Tự chọn)"] + list(PRESETS))
    if uni == "✍️ Tự nhập":
        symbols = [s.strip().upper() for s in st.text_input("Danh sách mã (cách nhau dấu phẩy)", "FPT,HPG,VCB,MWG").split(",")]
    elif uni == "⭐ Danh mục theo dõi":
        wl = Database().get_watchlist()
        symbols = wl["symbol"].tolist() if not wl.empty else []
    else:
        symbols = BASKETS.get(uni, [])
    st.caption(f"{len(symbols)} mã · mỗi mã cần vài lượt gọi dữ liệu nên nhóm lớn sẽ mất vài phút ở lần đầu; "
               "kết quả được lưu trong ngày.")

    filters = list(PRESETS.get(preset, []))
    with st.expander("⚙️ Điều kiện lọc", expanded=preset == "(Tự chọn)"):
        cols = st.columns(2)
        for i, (key, (label, op, lo, hi, default)) in enumerate(_FILTERABLE.items()):
            with cols[i % 2]:
                preset_thr = next((t for c, o, t in filters if c == key), None)
                on = st.checkbox(label, value=preset_thr is not None, key=f"f_on_{key}")
                thr = st.slider(label, lo, hi, float(preset_thr if preset_thr is not None else default),
                                key=f"f_thr_{key}", label_visibility="collapsed")
                filters = [f for f in filters if f[0] != key]
                if on:
                    filters.append((key, op, thr))

    if st.button("▶️ Chạy bộ lọc", type="primary") and symbols:
        bar = st.progress(0.0, text="Đang tính chỉ số...")
        df = ScreenerService().run(symbols, progress=lambda i, n: bar.progress(i / n, text=f"Đã xử lý {i}/{n} mã"))
        bar.empty()
        st.session_state["screener_df"] = df

    df = st.session_state.get("screener_df")
    if df is None or df.empty:
        return
    res = ScreenerService.rank(ScreenerService.apply_filters(df, filters))
    st.markdown(f"**{len(res)}/{len(df)} mã đạt điều kiện**")
    show = res.rename(columns={**PROFILE_COLUMNS, "rank_score": "Điểm xếp hạng"})
    st.dataframe(show.round(2), use_container_width=True, hide_index=True)
    errors = df[df.get("error").notna()] if "error" in df.columns else pd.DataFrame()
    if not errors.empty:
        with st.expander(f"⚠️ {len(errors)} mã lỗi dữ liệu"):
            st.dataframe(errors[["symbol", "error"]], hide_index=True)
    st.download_button("⬇️ Tải CSV", show.to_csv(index=False).encode("utf-8-sig"),
                       file_name=f"loc_co_phieu_{datetime.now():%Y%m%d}.csv", mime="text/csv")
    st.caption("Điểm xếp hạng = bình quân thứ hạng phần trăm của ROE, tăng trưởng, P/E, P/B, nợ vay, động lượng "
               "trong nhóm đã lọc (P/E âm không được coi là rẻ). Mã thiếu số liệu ở tiêu chí nào thì bị loại khỏi tiêu chí đó.")
