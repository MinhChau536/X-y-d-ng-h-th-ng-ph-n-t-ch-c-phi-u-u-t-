"""
Page – Backtest Strategy
"""
import streamlit as st
from services.stock_service import get_repo
import pandas as pd

from services.stock_service import StockService
from analytics.backtesting import BacktestEngine
from components.charts import backtest_equity_curve
from components.metrics import section_header, warning_box
from data.data_repository import DataRepository




def render():
    st.markdown("""
    <div class="page-header">
        <h1 style="font-size:22px;font-weight:800;color:#e6edf3;margin:0">
            🔬 Backtest Chiến Lược
        </h1>
        <p style="font-size:13px;color:#8b949e;margin:4px 0 0 0">
            Kiểm định chiến lược đầu tư trên dữ liệu lịch sử – Không look-ahead bias
        </p>
    </div>
    """, unsafe_allow_html=True)

    st.warning("⚠️ Kết quả backtest không đảm bảo hiệu quả tương lai. Cẩn thận overfitting.")

    col1, col2, col3 = st.columns(3)
    with col1:
        symbol = st.text_input("Mã cổ phiếu", value=st.session_state.get("current_symbol", "FPT"), key="bt_symbol").upper().strip()
    with col2:
        days = st.selectbox("Khoảng thời gian", [365, 730, 1095, 1825], index=1,
                             format_func=lambda d: f"{d//365} năm")
    with col3:
        strategy = st.selectbox("Chiến lược", [
            "MA Crossover (20/50)",
            "RSI Mean Reversion",
            "Custom Rules",
        ])

    # Strategy params
    with st.expander("⚙️ Tùy chỉnh tham số"):
        col_a, col_b = st.columns(2)
        with col_a:
            initial_capital = st.number_input("Vốn ban đầu (VND)", value=100_000_000, step=10_000_000)
            commission = st.number_input("Phí GD (%)", value=0.15, step=0.01) / 100
        with col_b:
            slippage = st.number_input("Trượt giá (%)", value=0.1, step=0.05) / 100

        if strategy == "Custom Rules":
            c1, c2 = st.columns(2)
            with c1:
                use_sma50 = st.checkbox("Giá > SMA50", value=True)
                use_sma_cross = st.checkbox("SMA20 > SMA50", value=True)
            with c2:
                rsi_min = st.slider("RSI min", 30, 70, 50)
                rsi_max = st.slider("RSI max", 50, 90, 70)
                exit_rsi = st.slider("RSI thoát lệnh (chốt lời)", 60, 95, 80)
            st.caption(
                "Thoát lệnh khi: giá < SMA50 hoặc SMA20 < SMA50 (nếu điều kiện tương ứng được bật), "
                "hoặc RSI vượt ngưỡng thoát lệnh."
            )

    run_btn = st.button("▶️ Chạy Backtest", type="primary")

    if run_btn and symbol:
        with st.spinner(f"Đang chạy backtest {symbol} ({days//365} năm)..."):
            price_df = get_repo().get_price_history(symbol, days=days)
            if price_df.empty:
                st.error("Không có dữ liệu giá")
                return

            engine = BacktestEngine(price_df, initial_capital, commission, slippage)

            if strategy == "MA Crossover (20/50)":
                signal = engine.ma_crossover_strategy(engine.df, fast=20, slow=50)
                strategy_name = "MA Crossover 20/50"
            elif strategy == "RSI Mean Reversion":
                signal = engine.rsi_strategy(engine.df)
                strategy_name = "RSI Mean Reversion"
            else:
                signal = engine.custom_strategy(
                    engine.df,
                    price_above_sma50=use_sma50,
                    sma20_above_sma50=use_sma_cross,
                    rsi_min=rsi_min,
                    rsi_max=rsi_max,
                    exit_rsi=exit_rsi,
                )
                strategy_name = "Custom Strategy"

            results = engine.run(signal, strategy_name)
            benchmark = engine.buy_and_hold_benchmark()

        if "error" in results:
            st.error(results["error"])
            return

        # ── Performance metrics ──
        section_header("Kết quả hiệu suất")
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Tổng lợi nhuận", f"{results['total_return_pct']:.1f}%",
                      delta=f"vs BH: {results['total_return_pct'] - benchmark.get('total_return_pct', 0):.1f}%")
        with col2:
            st.metric("CAGR", f"{results['cagr_pct']:.1f}%")
        with col3:
            st.metric("Max Drawdown", f"{results['max_drawdown_pct']:.1f}%")
        with col4:
            st.metric("Sharpe Ratio", f"{results['sharpe_ratio']:.2f}")

        col5, col6, col7, col8 = st.columns(4)
        with col5:
            st.metric("Win Rate", f"{results['win_rate_pct']:.1f}%")
        with col6:
            st.metric("Profit Factor", f"{results['profit_factor']:.2f}")
        with col7:
            st.metric("Số giao dịch", results['n_trades'])
        with col8:
            st.metric("Biến động (năm hóa)", f"{results['volatility_pct']:.1f}%")

        # ── Compare with benchmark ──
        section_header("So sánh với Buy & Hold")
        compare_df = pd.DataFrame([
            {"Chiến lược": results.get("strategy_name", "Strategy"),
             "Tổng LN (%)": results["total_return_pct"],
             "CAGR (%)": results["cagr_pct"],
             "Max DD (%)": results["max_drawdown_pct"],
             "Sharpe": results["sharpe_ratio"],
             "Biến động (%)": results["volatility_pct"]},
            {"Chiến lược": "Buy & Hold",
             "Tổng LN (%)": benchmark.get("total_return_pct", 0),
             "CAGR (%)": benchmark.get("cagr_pct", 0),
             "Max DD (%)": benchmark.get("max_drawdown_pct", 0),
             "Sharpe": benchmark.get("sharpe_ratio", 0),
             "Biến động (%)": benchmark.get("volatility_pct", 0)},
        ])
        st.dataframe(compare_df, use_container_width=True, hide_index=True)

        # ── Equity curve ──
        section_header("Đường vốn (Equity Curve)")
        index_df = get_repo().get_index_history("VNINDEX", days=days)
        fig = backtest_equity_curve(results.get("portfolio_values", []), index_df)
        st.plotly_chart(fig, use_container_width=True)

        # ── Trade log ──
        trade_log = results.get("trade_log", [])
        if trade_log:
            section_header(f"Nhật ký giao dịch ({len(trade_log)} lệnh)")
            trades_df = pd.DataFrame(trade_log)
            st.dataframe(trades_df, use_container_width=True, hide_index=True)

        # Warnings
        for w in results.get("warnings", []):
            st.warning(w)
