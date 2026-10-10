"""
Page 2 – Stock Analysis (Phân tích cổ phiếu)
"""
import streamlit as st
import pandas as pd
from datetime import datetime, timedelta

from services.stock_service import StockService
from components.charts import candlestick_chart, score_gauge
from components.metrics import (
    section_header, warning_box, render_company_header,
    score_badge, format_vnd, pct_color,
)
from config.constants import TIME_RANGES, SMA_PERIODS


def render():
    st.markdown("""
    <div class="page-header">
        <h1 style="font-size:22px;font-weight:800;color:#e6edf3;margin:0">
            🔍 Phân Tích Cổ Phiếu
        </h1>
        <p style="font-size:13px;color:#8b949e;margin:4px 0 0 0">
            Tra cứu và phân tích toàn diện một cổ phiếu
        </p>
    </div>
    """, unsafe_allow_html=True)

    # ── Symbol input ──
    col1, col2, col3 = st.columns([2, 1, 1])
    with col1:
        symbol = st.text_input(
            "Nhập mã cổ phiếu",
            value=st.session_state.get("current_symbol", "FPT"),
            placeholder="VD: FPT, HPG, VCB...",
            key="stock_symbol_input",
        ).upper().strip()
    with col2:
        time_range = st.selectbox(
            "Khoảng thời gian",
            options=list(TIME_RANGES.keys()),
            format_func=lambda k: TIME_RANGES[k][0],
            index=2,
        )
    with col3:
        st.markdown("<br>", unsafe_allow_html=True)
        analyze_btn = st.button("🔍 Phân Tích", type="primary", use_container_width=True)

    # Custom date range
    if time_range == "TT":
        cc1, cc2 = st.columns(2)
        with cc1:
            start_date = st.date_input("Từ ngày", value=datetime.now() - timedelta(days=365))
        with cc2:
            end_date = st.date_input("Đến ngày", value=datetime.now())
        days = (end_date - start_date).days
    else:
        days = TIME_RANGES[time_range][1]

    if not symbol:
        st.info("Vui lòng nhập mã cổ phiếu để bắt đầu phân tích.")
        return

    # Cache session
    if analyze_btn or symbol != st.session_state.get("last_analyzed"):
        st.session_state["current_symbol"] = symbol
        st.session_state["last_analyzed"] = symbol
        st.session_state.pop("stock_analysis", None)

    # Run analysis
    if "stock_analysis" not in st.session_state or st.session_state.get("last_analyzed") != symbol:
        with st.spinner(f"Đang phân tích {symbol}..."):
            try:
                svc = StockService(symbol, days=days)
                st.session_state["stock_analysis"] = svc.full_analysis()
                st.session_state["stock_service"] = svc
                st.session_state["last_analyzed"] = symbol
            except Exception as e:
                st.error(f"Lỗi phân tích: {e}")
                import traceback
                with st.expander("Chi tiết lỗi (gửi phần này khi báo lỗi)"):
                    st.code(traceback.format_exc())
                return

    analysis = st.session_state.get("stock_analysis", {})
    if not analysis:
        return
    if analysis.get("errors"):
        st.warning("Một số phần chưa xử lý được dữ liệu: " + ", ".join(analysis["errors"]) +
                   ". Các phần còn lại vẫn hiển thị bình thường.")
        with st.expander("Chi tiết lỗi (gửi phần này khi báo lỗi)"):
            for name, tb in analysis["errors"].items():
                st.markdown(f"**{name}**")
                st.code(tb)

    # ── Company header ──
    company = analysis.get("company_info", {})
    company["symbol"] = symbol
    current_price = analysis.get("current_price")
    render_company_header(company, current_price)

    # ── Key metrics row ──
    opp = analysis.get("opportunity_score", {})
    composite = opp.get("composite", {})
    score = composite.get("score")
    classification = composite.get("classification", {})

    metric_cols = st.columns(5)
    sub_scores = opp.get("sub_scores", {})
    metrics_display = [
        ("🎯 Cơ hội đầu tư", score, "/ 100"),
        ("📈 Kỹ thuật", sub_scores.get("technical"), "/ 100"),
        ("⚡ Động lượng", sub_scores.get("momentum"), "/ 100"),
        ("📊 Cơ bản", sub_scores.get("fundamental"), "/ 100"),
        ("💰 Định giá", sub_scores.get("valuation"), "/ 100"),
    ]
    for i, (label, val, suffix) in enumerate(metrics_display):
        with metric_cols[i]:
            display_val = f"{val:.0f}{suffix}" if val is not None else "N/A"
            st.metric(label=label, value=display_val)

    if score is not None:
        badge_html = score_badge(score, classification.get("label", ""))
        st.markdown(f"**Phân loại:** {badge_html}", unsafe_allow_html=True)

    st.markdown("---")

    # ── Tabs ──
    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "📈 Biểu đồ giá", "🔧 Kỹ thuật", "📊 Cơ bản", "💰 Định giá", "📰 Tin tức"
    ])

    tech = analysis.get("technical", {})
    tech_data = tech.get("data", pd.DataFrame())

    # ── Tab 1: Price chart ──
    with tab1:
        if tech.get("available") and not tech_data.empty:
            col_chart, col_settings = st.columns([4, 1])
            with col_settings:
                st.markdown("**Đường MA**")
                show_sma20 = st.checkbox("SMA 20", value=True)
                show_sma50 = st.checkbox("SMA 50", value=True)
                show_sma200 = st.checkbox("SMA 200", value=False)
                show_volume = st.checkbox("Khối lượng", value=True)

            ma_cols = []
            if show_sma20 and "SMA_20" in tech_data.columns:
                ma_cols.append("SMA_20")
            if show_sma50 and "SMA_50" in tech_data.columns:
                ma_cols.append("SMA_50")
            if show_sma200 and "SMA_200" in tech_data.columns:
                ma_cols.append("SMA_200")

            with col_chart:
                fig = candlestick_chart(tech_data, symbol, show_volume=show_volume,
                                        ma_cols=ma_cols, height=550)
                st.plotly_chart(fig, use_container_width=True)
        else:
            warning_box(f"Không có dữ liệu giá cho {symbol}: {tech.get('reason', '')}")

    # ── Tab 2: Technical ──
    with tab2:
        if tech.get("available"):
            signals = tech.get("signals", {})
            score_data = tech.get("score", {})

            c1, c2 = st.columns([1, 2])
            with c1:
                st.plotly_chart(score_gauge(score_data.get("score"), "Điểm kỹ thuật"), use_container_width=True)

            with c2:
                section_header("Tín hiệu chỉ báo")
                trend = signals.get("trend", {})
                if trend:
                    color = trend.get("color", "#8b949e")
                    st.markdown(
                        f'<div style="font-size:16px;font-weight:700;color:{color};">'
                        f'Xu hướng: {trend.get("name", "N/A")}</div>',
                        unsafe_allow_html=True,
                    )
                    for c in trend.get("criteria", []):
                        st.caption(f"  • {c}")

            # Signals table
            sig_rows = []
            for key, data in signals.items():
                if key in ["trend", "support_resistance"] or not isinstance(data, dict):
                    continue
                sig_rows.append({
                    "Chỉ báo": key.upper(),
                    "Tín hiệu": data.get("signal", data.get("cross", "N/A")),
                })
            if sig_rows:
                st.dataframe(pd.DataFrame(sig_rows), use_container_width=True, hide_index=True)

            # S/R
            sr = signals.get("support_resistance", {})
            if sr:
                c1, c2 = st.columns(2)
                with c1:
                    st.markdown("**🛡️ Hỗ trợ:**")
                    for v in sr.get("support", []):
                        st.markdown(f"• {v:,.0f}")
                with c2:
                    st.markdown("**🚧 Kháng cự:**")
                    for v in sr.get("resistance", []):
                        st.markdown(f"• {v:,.0f}")

            # RSI + MACD charts
            if not tech_data.empty:
                from components.charts import rsi_chart, macd_chart
                if "RSI" in tech_data.columns:
                    st.plotly_chart(rsi_chart(tech_data), use_container_width=True)
                if "MACD" in tech_data.columns:
                    st.plotly_chart(macd_chart(tech_data), use_container_width=True)
        else:
            warning_box(f"Không có dữ liệu kỹ thuật: {tech.get('reason', '')}")

    # ── Tab 3: Fundamental ──
    with tab3:
        fund = analysis.get("fundamental", {})
        if fund.get("available"):
            f_score = fund.get("score", {})
            f_metrics = fund.get("metrics", {})

            c1, c2 = st.columns([1, 2])
            with c1:
                st.plotly_chart(score_gauge(f_score.get("score"), "Điểm cơ bản"), use_container_width=True)
                if f_score.get("note"):
                    st.caption(f_score["note"])
            with c2:
                section_header("Chỉ số tài chính chính")
                rm = f_metrics.get("return_metrics", {})
                rp = f_metrics.get("revenue_profit", {})
                debt = f_metrics.get("debt", {})

                rows = []
                if rm.get("roe") is not None:
                    rows.append(("ROE", f"{rm['roe']:.1f}%"))
                if rm.get("roa") is not None:
                    rows.append(("ROA", f"{rm['roa']:.1f}%"))
                if rp.get("net_margin") is not None:
                    rows.append(("Biên LN ròng", f"{rp['net_margin']:.1f}%"))
                if debt.get("debt_to_equity") is not None:
                    rows.append(("Nợ/VCSH", f"{debt['debt_to_equity']:.2f}x"))

                if rows:
                    for label, val in rows:
                        st.metric(label=label, value=val)

            # Warnings
            all_warnings = (
                rp.get("warnings", []) +
                debt.get("warnings", []) +
                f_metrics.get("cashflow", {}).get("warnings", [])
            )
            if all_warnings:
                section_header("⚠️ Cảnh báo")
                for w in all_warnings:
                    warning_box(w)

            # BCTC chuẩn hóa (tóm tắt) – bảng đầy đủ & tải Excel ở trang "📑 Báo Cáo Tài Chính"
            from reports.excel_export import statement_table
            fin = analysis.get("financials") or {}
            data = fin.get("data")
            st.markdown("---")
            section_header("Dữ liệu tài chính (tỷ đồng)", f_metrics.get("basis", ""))
            if data is None or data.empty:
                st.info("Không lấy được BCTC – xem trang 🛰️ Nguồn dữ liệu.")
            else:
                for tab, code in zip(st.tabs(["KQKD", "CĐKT", "Lưu chuyển TT", "Chỉ số"]), ["is", "bs", "cf", "ratios"]):
                    with tab:
                        if code == "ratios":
                            tbl = (analysis.get("financial_summary") or {}).get("table")
                            if tbl is not None and not tbl.empty:
                                st.dataframe(tbl.drop(columns=["_key", "_fmt"]).round(2), use_container_width=True, hide_index=True)
                            continue
                        t = statement_table(data, code)
                        if t.empty:
                            st.info("Không có số liệu")
                        else:
                            st.dataframe(t.set_index("Chỉ tiêu").round(0), use_container_width=True)
                st.caption("Xem đầy đủ nhiều năm, nguồn từng ô và tải Excel ở trang 📑 Báo Cáo Tài Chính.")
        else:
            st.info("Đang tải dữ liệu tài chính...")

    # ── Tab 4: Valuation ──
    with tab4:
        val = analysis.get("valuation", {})
        val_score = val.get("score", {})
        rel_val = val_score.get("relative_valuation", {})

        c1, c2 = st.columns([1, 2])
        with c1:
            st.plotly_chart(score_gauge(val_score.get("score"), "Điểm định giá"), use_container_width=True)
        with c2:
            section_header("Định giá tương đối")
            rows = []
            for label, key, fmt in [
                ("Giá thị trường", "current_price", "{:,.0f} VND"),
                ("P/E", "pe", "{:.1f}x"),
                ("P/B", "pb", "{:.2f}x"),
                ("EPS", "eps", "{:,.0f} VND"),
                ("BVPS", "bvps", "{:,.0f} VND"),
                ("Giá trị hợp lý (TB)", "average_fair_value", "{:,.0f} VND"),
            ]:
                v = rel_val.get(key)
                if v is not None:
                    try:
                        rows.append({"Chỉ số": label, "Giá trị": fmt.format(v)})
                    except Exception:
                        rows.append({"Chỉ số": label, "Giá trị": str(v)})

            upside = rel_val.get("upside")
            if upside is not None:
                rows.append({"Chỉ số": "Upside/Downside", "Giá trị": f"{upside:.1f}%"})
            if rel_val.get("sector_pe") is not None:
                rows.append({"Chỉ số": "P/E tham chiếu",
                             "Giá trị": f"{rel_val['sector_pe']:.1f}x – {rel_val.get('sector_pe_source', '')}"})
            if rel_val.get("sector_pb") is not None:
                rows.append({"Chỉ số": "P/B tham chiếu",
                             "Giá trị": f"{rel_val['sector_pb']:.2f}x – {rel_val.get('sector_pb_source', '')}"})

            if rows:
                st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

        # DCF section
        dcf = val_score.get("dcf", {})
        if dcf.get("available"):
            section_header("DCF (Đơn giản)")
            st.info("⚠️ DCF đơn giản dựa trên EPS – chỉ mang tính tham khảo")
            dcf_cols = st.columns(3)
            for i, (name, val) in enumerate(dcf.get("scenarios", {}).items()):
                with dcf_cols[i]:
                    st.metric(label=f"Kịch bản {name}", value=f"{val:,.0f} VND")
            st.markdown("**Giả định:**")
            for k, v in dcf.get("assumptions", {}).items():
                st.caption(f"• {k}: {v}")

    # ── Tab 5: Company News ──
    with tab5:
        from pages.company_news import render as render_company_news
        render_company_news()
