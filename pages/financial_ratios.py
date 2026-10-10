"""
Trang – Chỉ số tài chính tính trực tiếp từ BCTC: sinh lời, thanh khoản, đòn bẩy, hiệu quả,
tăng trưởng, dòng tiền, định giá tại giá hiện tại, DuPont, Piotroski F-score, Altman Z''-score.
"""
from __future__ import annotations

import pandas as pd
import streamlit as st

from analytics.financial_ratios import RATIO_META, VALUATION_META
from analytics.period_utils import key_to_label
from components.ui import bar_chart, fmt_num, line_chart, page_header, source_caption, symbol_input
from services.stock_service import StockService


def _fmt(v, fmt):
    if fmt == "%":
        return fmt_num(v, 1, "%")
    if fmt == "x":
        return fmt_num(v, 2, "x")
    if fmt == "days":
        return fmt_num(v, 0)
    if fmt == "vnd":
        return fmt_num(v / 1e9, 0, " tỷ") if v is not None and pd.notna(v) and abs(v) > 1e7 else fmt_num(v, 0)
    return fmt_num(v, 2)


def render():
    page_header("🧮 Chỉ Số Tài Chính", "Tính trực tiếp từ BCTC đã chuẩn hóa – không phụ thuộc bảng chỉ số dựng sẵn của nhà cung cấp")
    c1, c2, c3 = st.columns([2, 1, 1])
    with c1:
        symbol = symbol_input("fr_symbol")
    with c2:
        period = st.selectbox("Kỳ", ["year", "quarter"], format_func=lambda p: "Năm" if p == "year" else "Quý (TTM)",
                              key="fr_period")
    with c3:
        years = st.slider("Số năm", 3, 15, 8, key="fr_years")
    if not symbol:
        return
    with st.spinner("Đang tính chỉ số..."):
        svc = StockService(symbol, fin_period=period, fin_years=years)
        summ = svc.financial_summary(period)
    ratios = summ.get("ratios", pd.DataFrame())
    if ratios is None or ratios.empty:
        st.error("Không đủ BCTC để tính chỉ số. Kiểm tra trang 📑 Báo cáo tài chính.")
        return
    if summ.get("is_bank"):
        st.info("🏦 Doanh nghiệp ngân hàng: một số chỉ số phi tài chính (biên gộp, vòng quay tồn kho, Z-score) không áp dụng.")

    # ── Định giá tại giá hiện tại ──
    val = summ.get("valuation") or {}
    st.markdown("#### 💰 Định giá tại giá hiện tại")
    cols = st.columns(6)
    for col, key in zip(cols, ["pe", "pb", "ps", "ev_ebitda", "dividend_yield", "earnings_yield"]):
        label, fmt = VALUATION_META[key]
        col.metric(label, _fmt(val.get(key), fmt))
    source_caption(f"Vốn hóa {fmt_num((val.get('market_cap') or 0) / 1e9, 0) if val.get('market_cap') else '–'} tỷ đ · "
                   f"Giá {fmt_num(val.get('price'), 0)} đ · EPS {fmt_num(val.get('eps_ttm'), 0)} đ · BVPS "
                   f"{fmt_num(val.get('bvps'), 0)} đ · BCTC kỳ {val.get('as_of_period') or '–'}"
                   + (" (TTM)" if period == "quarter" else ""))

    # ── Bảng chỉ số theo nhóm ──
    st.markdown("#### 📋 Bảng chỉ số theo kỳ")
    r = ratios.iloc[-(years if period == "year" else years * 4):]
    periods = [key_to_label(k) for k in r.index]
    groups = {}
    for key, (label, group, fmt, better) in RATIO_META.items():
        if key in r.columns and r[key].notna().any():
            groups.setdefault(group, []).append((key, label, fmt))
    tabs = st.tabs(list(groups))
    for tab, (group, items) in zip(tabs, groups.items()):
        with tab:
            table = pd.DataFrame({label: [_fmt(v, fmt) for v in r[key].tolist()] for key, label, fmt in items},
                                 index=periods).T
            st.dataframe(table, use_container_width=True)
            plot_keys = [(k, l) for k, l, f in items if f in ("%", "x")][:4]
            if plot_keys:
                st.plotly_chart(line_chart(periods, {l: r[k].tolist() for k, l in plot_keys}, group),
                                use_container_width=True)

    # ── DuPont ──
    d = summ.get("dupont")
    if d is not None and not d.empty:
        st.markdown("#### 🔍 Phân tích DuPont (ROE = Biên LN ròng × Vòng quay tài sản × Đòn bẩy)")
        d = d.loc[d.index.isin(r.index)]
        dp = [key_to_label(k) for k in d.index]
        c1, c2 = st.columns(2)
        with c1:
            st.plotly_chart(line_chart(dp, {"ROE theo DuPont (%)": d["roe_dupont"].tolist(),
                                            "Biên LN ròng (%)": d["net_margin"].tolist()}, "ROE & biên lợi nhuận"),
                            use_container_width=True)
        with c2:
            st.plotly_chart(line_chart(dp, {"Vòng quay tài sản (x)": d["asset_turnover"].tolist(),
                                            "Đòn bẩy TTS/VCSH (x)": d["equity_multiplier"].tolist()}, "Hiệu quả & đòn bẩy"),
                            use_container_width=True)
        st.caption("DuPont dùng LNST toàn công ty và VCSH bình quân nên có thể chênh nhẹ so với ROE tính trên LNST cổ đông mẹ.")

    # ── Sức khỏe tài chính ──
    st.markdown("#### 🩺 Sức khỏe tài chính")
    c1, c2, c3 = st.columns(3)
    pio = summ.get("piotroski") or {}
    with c1:
        st.metric("Piotroski F-score", f"{pio['score']}/{pio['max']}" if pio.get("score") is not None else "N/A",
                  help="9 tiêu chí về lợi nhuận, đòn bẩy/thanh khoản và hiệu quả hoạt động (cần BCTC năm)")
        for chk in pio.get("checks", []):
            icon = "✅" if chk["pass"] else ("❌" if chk["pass"] is False else "➖")
            st.caption(f"{icon} {chk['name']}")
    alt = summ.get("altman") or {}
    with c2:
        st.metric("Altman Z''-score", fmt_num(alt.get("score"), 2), alt.get("zone") or alt.get("note"),
                  delta_color="off")
        st.caption("> 5,85 an toàn · 4,35–5,85 cảnh báo · < 4,35 nguy cơ (bản cho thị trường mới nổi)")
    with c3:
        cg = summ.get("cagr") or {}
        st.metric("CAGR doanh thu 3 năm", fmt_num(cg.get("revenue_3y"), 1, "%"))
        st.metric("CAGR LNST 5 năm", fmt_num(cg.get("net_income_5y"), 1, "%"))
