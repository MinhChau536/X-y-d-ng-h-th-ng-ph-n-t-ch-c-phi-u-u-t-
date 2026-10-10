"""
Page – Technical Analysis (detailed)
"""
import streamlit as st
import pandas as pd

from services.stock_service import StockService
from components.charts import (
    candlestick_chart, rsi_chart, macd_chart, bollinger_chart, score_gauge,
)
from components.metrics import section_header, warning_box


def render():
    st.markdown("""
    <div class="page-header">
        <h1 style="font-size:22px;font-weight:800;color:#e6edf3;margin:0">
            📈 Phân Tích Kỹ Thuật
        </h1>
        <p style="font-size:13px;color:#8b949e;margin:4px 0 0 0">
            Chỉ báo kỹ thuật chi tiết – Tất cả tính toán bằng thuật toán
        </p>
    </div>
    """, unsafe_allow_html=True)

    col1, col2 = st.columns([2, 1])
    with col1:
        symbol = st.text_input("Mã cổ phiếu", value=st.session_state.get("current_symbol", "FPT"),
                               key="ta_symbol").upper().strip()
    with col2:
        days = st.selectbox("Khoảng thời gian (ngày)", [90, 180, 365, 730], index=2)

    if st.button("Tính toán chỉ báo", type="primary") or symbol:
        with st.spinner(f"Đang tính chỉ báo cho {symbol}..."):
            try:
                svc = StockService(symbol, days=days)
                tech = svc.technical_analysis()
            except Exception as e:
                st.error(f"Lỗi: {e}")
                return

        if not tech.get("available"):
            warning_box(f"Không có dữ liệu: {tech.get('reason', '')}")
            return

        data = tech.get("data", pd.DataFrame())
        signals = tech.get("signals", {})
        score_data = tech.get("score", {})

        # ── Overview metrics ──
        col1, col2, col3, col4 = st.columns(4)
        trend = signals.get("trend", {})
        rsi_sig = signals.get("rsi", {})
        macd_sig = signals.get("macd", {})
        vol_sig = signals.get("volume", {})

        with col1:
            st.metric("Xu hướng", trend.get("name", "N/A"))
        with col2:
            rsi_v = rsi_sig.get("value")
            st.metric("RSI(14)", f"{rsi_v:.1f}" if rsi_v else "N/A", rsi_sig.get("signal", ""))
        with col3:
            st.metric("MACD", macd_sig.get("cross", "N/A"))
        with col4:
            st.metric("Rel Volume", f"{vol_sig.get('relative_volume', 0):.1f}x" if vol_sig else "N/A")

        # ── Charts ──
        section_header("Biểu đồ nến & MA")
        ma_options = ["SMA_20", "SMA_50", "SMA_200"]
        selected_mas = [c for c in ma_options if c in data.columns]
        fig_candle = candlestick_chart(data, symbol, show_volume=True, ma_cols=selected_mas, height=500)
        st.plotly_chart(fig_candle, use_container_width=True)

        col_rsi, col_macd = st.columns(2)
        with col_rsi:
            if "RSI" in data.columns:
                st.plotly_chart(rsi_chart(data), use_container_width=True)
            else:
                st.info("Không đủ dữ liệu tính RSI")
        with col_macd:
            if "MACD" in data.columns:
                st.plotly_chart(macd_chart(data), use_container_width=True)
            else:
                st.info("Không đủ dữ liệu tính MACD")

        # Bollinger
        if all(c in data.columns for c in ["BB_upper", "BB_mid", "BB_lower"]):
            st.plotly_chart(bollinger_chart(data, symbol), use_container_width=True)

        # ── Indicator Table ──
        section_header("Bảng chỉ báo hiện tại")
        if not data.empty:
            last = data.iloc[-1]
            ind_rows = []
            indicators = [
                ("Giá đóng cửa", "close", "{:,.0f}"),
                ("SMA 20", "SMA_20", "{:,.0f}"),
                ("SMA 50", "SMA_50", "{:,.0f}"),
                ("SMA 200", "SMA_200", "{:,.0f}"),
                ("EMA 12", "EMA_12", "{:,.0f}"),
                ("EMA 26", "EMA_26", "{:,.0f}"),
                ("RSI(14)", "RSI", "{:.2f}"),
                ("MACD", "MACD", "{:.4f}"),
                ("MACD Signal", "MACD_signal", "{:.4f}"),
                ("BB Upper", "BB_upper", "{:,.0f}"),
                ("BB Lower", "BB_lower", "{:,.0f}"),
                ("ATR(14)", "ATR", "{:.2f}"),
                ("ADX(14)", "ADX", "{:.2f}"),
                ("MFI(14)", "MFI", "{:.2f}"),
                ("CMF(20)", "CMF", "{:.4f}"),
                ("ROC", "ROC", "{:.2f}"),
                ("Rel Volume", "RelVol", "{:.2f}x"),
            ]
            for name, col, fmt in indicators:
                val = last.get(col)
                if val is not None and not pd.isna(val):
                    try:
                        ind_rows.append({"Chỉ báo": name, "Giá trị": fmt.format(float(val))})
                    except Exception:
                        ind_rows.append({"Chỉ báo": name, "Giá trị": str(val)})
            if ind_rows:
                st.dataframe(pd.DataFrame(ind_rows), use_container_width=True, hide_index=True)

        # ── Score breakdown ──
        section_header("Phân tích điểm kỹ thuật")
        c1, c2 = st.columns([1, 2])
        with c1:
            from components.charts import score_gauge
            st.plotly_chart(score_gauge(score_data.get("score"), "Điểm kỹ thuật"), use_container_width=True)
        with c2:
            components = score_data.get("components", {})
            comp_rows = []
            for k, v in components.items():
                comp_rows.append({
                    "Nhóm": k.replace("_", " ").title(),
                    "Điểm": f"{v.get('score', 'N/A')}/{v.get('max', 100)}",
                })
            if comp_rows:
                st.dataframe(pd.DataFrame(comp_rows), use_container_width=True, hide_index=True)
