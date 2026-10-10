"""Trang – Danh mục theo dõi, cảnh báo giá và bảng tin hằng ngày của các mã đang theo dõi."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from components.ui import fmt_num, page_header
from services.company_news_service import CompanyNewsService
from services.watchlist_service import CONDITIONS, WatchlistService


def render():
    page_header("⭐ Danh Mục Theo Dõi & Cảnh Báo", "Theo dõi giá gần nhất (DNSE), đặt cảnh báo, xem tin tức mới mỗi ngày")
    ws = WatchlistService()

    c1, c2, c3 = st.columns([2, 3, 1])
    with c1:
        new = st.text_input("Thêm mã", value="", placeholder="VD: FPT").upper().strip()
    with c2:
        note = st.text_input("Ghi chú", value="")
    with c3:
        st.write("")
        if st.button("➕ Thêm", use_container_width=True) and new:
            ws.add(new, note)
            st.rerun()

    syms = ws.symbols()
    if not syms:
        st.info("Danh mục trống. Thêm mã để theo dõi; script cập nhật hằng ngày sẽ lấy giá và tin tức cho các mã này.")
        return

    # Cảnh báo vừa kích hoạt
    triggered = ws.evaluate()
    for t in triggered:
        st.warning(f"🔔 {t['symbol']}: {t['condition']} {fmt_num(t['threshold'], 2)} — giá hiện tại "
                   f"{fmt_num(t['price'], 0)} đ, thay đổi {fmt_num(t['change_pct'], 2, '%')}, RSI {fmt_num(t['rsi'], 1)}")

    with st.spinner("Đang cập nhật giá..."):
        snap = ws.snapshot()
    if not snap.empty:
        view = pd.DataFrame({
            "Mã": snap["symbol"], "Giá (đ)": snap["price"].map(lambda v: fmt_num(v, 0)),
            "% phiên": snap["change_pct"].map(lambda v: fmt_num(v, 2, "%")),
            "% 1 tháng": snap["change_1m_pct"].map(lambda v: fmt_num(v, 2, "%")),
            "RSI(14)": snap["rsi"].map(lambda v: fmt_num(v, 1)), "Nguồn giá": snap["source"],
        })
        st.dataframe(view, use_container_width=True, hide_index=True)
    rm = st.selectbox("Bỏ theo dõi mã", [""] + syms)
    if rm and st.button("Xóa khỏi danh mục"):
        ws.remove(rm)
        st.rerun()

    st.markdown("#### 🔔 Cảnh báo giá")
    c1, c2, c3, c4 = st.columns([1, 2, 1, 1])
    with c1:
        a_sym = st.selectbox("Mã", syms, key="al_sym")
    with c2:
        cond = st.selectbox("Điều kiện", list(CONDITIONS), format_func=CONDITIONS.get)
    with c3:
        thr = st.number_input("Ngưỡng", value=0.0, step=100.0 if cond.startswith("price") else 1.0)
    with c4:
        st.write("")
        if st.button("Tạo cảnh báo", use_container_width=True):
            ws.add_alert(a_sym, cond, thr)
            st.rerun()
    al = ws.alerts()
    if not al.empty:
        al_view = al[["id", "symbol", "condition_label", "threshold", "active", "triggered_at", "triggered_price"]]
        st.dataframe(al_view.rename(columns={"symbol": "Mã", "condition_label": "Điều kiện", "threshold": "Ngưỡng",
                                             "active": "Đang bật", "triggered_at": "Kích hoạt lúc",
                                             "triggered_price": "Giá khi kích hoạt"}),
                     use_container_width=True, hide_index=True)
        del_id = st.selectbox("Xóa cảnh báo #", [None] + al["id"].tolist())
        if del_id and st.button("Xóa cảnh báo"):
            ws.delete_alert(int(del_id))
            st.rerun()

    st.markdown("#### 📰 Bảng tin các mã đang theo dõi")
    days = st.select_slider("Trong vòng", [1, 3, 7, 14, 30], value=7, format_func=lambda d: f"{d} ngày")
    if st.button("🔄 Thu thập tin mới"):
        svc = CompanyNewsService()
        with st.spinner("Đang thu thập tin..."):
            for s in syms:
                svc.get_company_news(s, force_refresh=True)
    feed = CompanyNewsService.feed(syms, days=days)
    if feed.empty:
        st.info("Chưa có tin đã lưu trong khoảng này. Bấm “Thu thập tin mới” hoặc chạy script cập nhật hằng ngày.")
        return
    icon = {"positive": "🟢", "negative": "🔴", "neutral": "⚪"}
    for _, n in feed.head(60).iterrows():
        when = pd.to_datetime(n["published_at"]).strftime("%d/%m %H:%M") if pd.notna(n["published_at"]) else "—"
        title = f"[{n['title']}]({n['url']})" if n.get("url") else n["title"]
        st.markdown(f"{icon.get(n['sentiment'], '⚪')} **{n['symbol']}** · {when} · {title}  "
                    f"<span style='font-size:11px;color:#64748b'>({n['source']})</span>", unsafe_allow_html=True)
