"""
Page – Portfolio Management (Danh mục đầu tư)
"""
import streamlit as st
import pandas as pd
from datetime import datetime

from services.portfolio_service import PortfolioService
from components.charts import portfolio_pie
from components.metrics import section_header, warning_box, format_vnd

svc = PortfolioService()


def render():
    st.markdown("""
    <div class="page-header">
        <h1 style="font-size:22px;font-weight:800;color:#e6edf3;margin:0">
            💼 Danh Mục Đầu Tư
        </h1>
        <p style="font-size:13px;color:#8b949e;margin:4px 0 0 0">
            Theo dõi danh mục cổ phiếu cá nhân
        </p>
    </div>
    """, unsafe_allow_html=True)

    portfolio_name = st.text_input("Tên danh mục", value="default", key="portfolio_name_input")

    # ── Add position ──
    with st.expander("➕ Thêm vị thế mới"):
        col1, col2, col3 = st.columns(3)
        with col1:
            new_symbol = st.text_input("Mã CP", key="new_sym").upper()
            new_qty = st.number_input("Số lượng (CP)", min_value=100, step=100, value=1000)
        with col2:
            new_price = st.number_input("Giá mua (VND)", min_value=1000, step=100, value=50000)
            new_date = st.date_input("Ngày mua", value=datetime.now())
        with col3:
            new_fee = st.number_input("Phí GD (%)", min_value=0.0, max_value=1.0,
                                       value=0.15, step=0.01, format="%.2f") / 100
            new_notes = st.text_area("Ghi chú", height=75)

        if st.button("Thêm vào danh mục", type="primary"):
            if new_symbol and new_qty > 0 and new_price > 0:
                svc.add_position(new_symbol, new_qty, new_price,
                                  str(new_date), new_fee, new_notes, portfolio_name)
                st.success(f"Đã thêm {new_symbol} vào danh mục '{portfolio_name}'")
                st.rerun()
            else:
                warning_box("Vui lòng nhập đầy đủ thông tin")

    st.markdown("---")

    # ── Portfolio display ──
    summary = svc.get_portfolio_summary(portfolio_name)

    if summary.get("empty"):
        st.info("Danh mục trống. Hãy thêm cổ phiếu bên trên.")
        return

    # Summary metrics
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Tổng vốn bỏ ra", format_vnd(summary["total_cost"], "tỷ"))
    with col2:
        st.metric("Giá trị hiện tại", format_vnd(summary["total_value"], "tỷ"))
    with col3:
        pnl = summary["total_pnl"]
        st.metric("Lãi/Lỗ chưa thực", format_vnd(pnl, "tỷ"),
                  delta=f"{summary['total_pct']:+.2f}%",
                  delta_color="normal" if pnl >= 0 else "inverse")
    with col4:
        st.metric("Số vị thế", summary["n_positions"])

    # Charts
    col_chart, col_table = st.columns([1, 2])
    positions_df = summary.get("positions", pd.DataFrame())

    with col_chart:
        if not positions_df.empty:
            fig = portfolio_pie(positions_df)
            st.plotly_chart(fig, use_container_width=True)

    with col_table:
        section_header("Chi tiết danh mục")
        if not positions_df.empty:
            display_df = positions_df[[
                "symbol", "quantity", "buy_price", "current_price",
                "unrealized_pnl", "unrealized_pct"
            ]].copy()
            display_df.columns = ["Mã", "Số lượng", "Giá mua", "Giá hiện tại", "Lãi/Lỗ", "% L/L"]
            st.dataframe(display_df, use_container_width=True, hide_index=True)

    # Delete
    section_header("Xóa vị thế")
    if not positions_df.empty:
        del_id = st.selectbox(
            "Chọn vị thế cần xóa",
            options=positions_df["id"].tolist(),
            format_func=lambda x: f"ID {x}: {positions_df[positions_df['id']==x]['symbol'].values[0]}",
        )
        if st.button("🗑️ Xóa vị thế", type="secondary"):
            svc.delete_position(del_id)
            st.success("Đã xóa vị thế")
            st.rerun()
