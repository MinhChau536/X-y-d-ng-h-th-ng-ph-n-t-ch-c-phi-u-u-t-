"""
STOCK ANALYTICS PRO – HỆ THỐNG PHÂN TÍCH CƠ HỘI ĐẦU TƯ CỔ PHIẾU VIỆT NAM
Main Application Entry Point.
"""
from __future__ import annotations

import logging
import os
import sys
from pathlib import Path
import streamlit as st

# Configure base path
BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from config.settings import settings
from config.constants import MARKET_INDICES
from assets.styles.main_style import load_css
from data.ticker_directory import (
    get_basket_names,
    get_formatted_options,
    get_ticker_label,
    extract_symbol_from_label,
    find_option_for_symbol,
)

# Import pages
from pages import (
    market_overview,
    stock_analysis,
    technical_analysis,
    opportunity_score,
    backtest,
    portfolio,
    pdf_report,
    company_news,
    financial_statements,
    financial_ratios,
    documents,
    screener,
    compare,
    watchlist,
    data_sources,
)

# Optional option_menu
try:
    from streamlit_option_menu import option_menu
    HAS_OPTION_MENU = True
except ImportError:
    HAS_OPTION_MENU = False

logging.basicConfig(level=getattr(logging, settings.LOG_LEVEL, logging.INFO))
logger = logging.getLogger(__name__)

# ─── Page Configuration ──────────────────────────────────────────────────────
st.set_page_config(
    page_title="Stock Analytics Pro - Phân Tích Cổ Phiếu Việt Nam",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─── Session State Initialization ───────────────────────────────────────────
if "theme" not in st.session_state:
    st.session_state["theme"] = "light"

if "current_symbol" not in st.session_state:
    st.session_state["current_symbol"] = "FPT"

if "nav_page" not in st.session_state:
    st.session_state["nav_page"] = "🏛️ Tổng Quan Thị Trường"

# Inject Active Theme CSS
st.markdown(load_css(st.session_state["theme"]), unsafe_allow_html=True)

# Hiệu ứng nền động (aurora + mạng hạt phản ứng theo chuột) – bật/tắt ở thanh bên
from components.background_fx import inject_background
if "bg_fx" not in st.session_state:
    st.session_state["bg_fx"] = True
inject_background(st.session_state["theme"], st.session_state["bg_fx"])


def render_sidebar():
    """Render modern sidebar navigation, theme switcher, and market badges."""
    with st.sidebar:
        is_light = st.session_state["theme"] == "light"

        # Theme Switcher
        st.markdown(
            f"<div style='font-size:11px;font-weight:700;letter-spacing:0.5px;text-transform:uppercase;margin-bottom:6px;color:{'#64748b' if is_light else '#8b949e'}'>CHẾ ĐỘ HIỂN THỊ</div>",
            unsafe_allow_html=True,
        )
        theme_pick = st.radio(
            "Theme",
            options=["☀️ Chế độ Sáng", "🌙 Chế độ Tối"],
            index=0 if is_light else 1,
            horizontal=True,
            label_visibility="collapsed",
            key="theme_switcher_select",
        )
        st.toggle("✨ Hiệu ứng nền động", key="bg_fx",
                  help="Nền gradient chuyển động + mạng hạt phản ứng theo chuột. Tắt nếu máy chạy chậm.")
        selected_theme = "light" if "Sáng" in theme_pick else "dark"
        if selected_theme != st.session_state["theme"]:
            st.session_state["theme"] = selected_theme
            st.rerun()

        # App branding header
        brand_border = "#e2e8f0" if is_light else "#30363d"
        brand_title = "#0284c7" if is_light else "#58a6ff"
        brand_sub = "#64748b" if is_light else "#8b949e"
        card_bg = "#ffffff" if is_light else "#161b22"
        card_border = "#e2e8f0" if is_light else "#30363d"
        ticker_color = "#16a34a" if is_light else "#00e676"

        # App branding header (STOCKWISE Platform)
        st.markdown(f"""
        <div style="background: {card_bg}; border: 1px solid {card_border}; border-radius: 12px; padding: 12px 14px; text-align: center; box-shadow: 0 2px 8px rgba(0,0,0,0.04); margin-bottom: 16px;">
            <div style="display:flex; align-items:center; justify-content:center; gap: 8px;">
                <span style="font-size: 22px;">☁️</span>
                <span style="font-size: 18px; font-weight: 800; color: {'#1e293b' if is_light else '#f1f5f9'}; letter-spacing: 0.5px;">STOCKWISE</span>
            </div>
            <div style="font-size: 9.5px; font-weight: 700; color: {brand_sub}; letter-spacing: 0.8px; margin-top: 3px;">FINANCIAL ANALYTICS PLATFORM</div>
        </div>
        """, unsafe_allow_html=True)

        # 1. Tra cứu cổ phiếu
        st.markdown(f"<p style='font-size:12px; font-weight:800; color:{'#1e293b' if is_light else '#f1f5f9'}; margin-bottom:6px;'>🔎 Tra cứu cổ phiếu</p>", unsafe_allow_html=True)
        curr_sym = st.session_state.get("current_symbol", "PNJ").strip().upper()

        st.markdown(f"<p style='font-size:11px; font-weight:600; color:{brand_sub}; margin-bottom:4px;'>Mã cổ phiếu</p>", unsafe_allow_html=True)
        col_in, col_btn = st.columns([3, 2])
        with col_in:
            direct_input = st.text_input(
                "Mã cổ phiếu",
                value=curr_sym,
                key=f"sidebar_direct_sym_{curr_sym}",
                label_visibility="collapsed",
                placeholder="VD: PNJ, FPT, VCB...",
            ).strip().upper()
        with col_btn:
            btn_apply = st.button("Áp dụng 🎯", key="btn_apply_direct_sym", use_container_width=True)

        # Optional CSV Upload
        with st.expander("📁 Hoặc tải CSV dữ liệu giá", expanded=False):
            uploaded_csv = st.file_uploader(
                "Hoặc tải CSV dữ liệu giá",
                type=["csv"],
                key="sidebar_csv_uploader",
                help="Hỗ trợ file CSV chứa dữ liệu giá OHLCV (tối đa 200MB)",
                label_visibility="collapsed",
            )
            if uploaded_csv is not None:
                st.caption(f"Đã nhận file: {uploaded_csv.name} ({uploaded_csv.size / 1024:.1f} KB)")

        # Basket / Sector filter selector
        with st.expander("🏷️ Bộ lọc ngành & rổ chỉ số", expanded=False):
            basket_names = get_basket_names()
            selected_basket = st.selectbox(
                "Lọc theo nhóm / ngành",
                options=basket_names,
                index=0,
                key="sidebar_basket_select",
                help="Lọc danh sách mã theo rổ chỉ số (VN30, HNX30) hoặc ngành kinh tế",
            )
            options = get_formatted_options(selected_basket)
            matched_opt = find_option_for_symbol(curr_sym, options)
            if matched_opt:
                def_idx = options.index(matched_opt)
            else:
                curr_label = get_ticker_label(curr_sym)
                options = [curr_label] + options
                def_idx = 0

            dropdown_pick = st.selectbox(
                "Tìm & chọn mã trong rổ",
                options=options,
                index=def_idx,
                key=f"sidebar_pick_{selected_basket}_{curr_sym}",
                label_visibility="collapsed",
            )
            dropdown_sym = extract_symbol_from_label(dropdown_pick)
            if dropdown_sym != curr_sym and dropdown_sym:
                st.session_state["current_symbol"] = dropdown_sym
                st.rerun()

        # Helper to sync all page widgets & state
        def sync_active_symbol(new_sym: str, switch_page: bool = True):
            new_sym = new_sym.strip().upper()
            if not new_sym:
                return
            st.session_state["current_symbol"] = new_sym
            st.session_state["stock_symbol_input"] = new_sym
            st.session_state["ta_symbol"] = new_sym
            st.session_state["score_symbol"] = new_sym
            st.session_state["bt_symbol"] = new_sym
            st.session_state["pdf_symbol"] = new_sym

            st.session_state.pop("stock_analysis", None)
            st.session_state.pop("last_analyzed", None)

            if switch_page and st.session_state.get("nav_page") == "🏛️ Tổng Quan Thị Trường":
                st.session_state["nav_page"] = "🔍 Phân Tích Cổ Phiếu"

        if btn_apply and direct_input:
            sync_active_symbol(direct_input, switch_page=True)
            st.rerun()

        # Display current active stock badge
        active_label = get_ticker_label(st.session_state["current_symbol"])
        st.markdown(
            f"""
            <div style="background:{card_bg}; border:1px solid {card_border}; border-radius:8px; padding:7px 10px; margin-top:6px; margin-bottom:14px; text-align:center; box-shadow: 0 1px 3px rgba(0,0,0,0.03);">
                <div style="font-size:10.5px; color:{brand_sub};">Đang chọn phân tích:</div>
                <div style="font-size:13.5px; font-weight:800; color:{ticker_color}; letter-spacing:0.5px; margin-top:2px; word-break:break-word;">
                    {active_label}
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        # 2. Khám phá (Navigation Menu)
        st.markdown(f"<p style='font-size:12px; font-weight:800; color:{'#1e293b' if is_light else '#f1f5f9'}; margin-bottom:6px;'>🧭 Khám phá</p>", unsafe_allow_html=True)
        menu_options = [
            "🏛️ Tổng Quan Thị Trường",
            "🔍 Phân Tích Cổ Phiếu",
            "📑 Báo Cáo Tài Chính",
            "🧮 Chỉ Số Tài Chính",
            "📚 Tài Liệu BCTN & BCTC",
            "📈 Phân Tích Kỹ Thuật",
            "📰 Tin Tức Doanh Nghiệp",
            "⭐ Điểm Cơ Hội Đầu Tư",
            "🔎 Bộ Lọc Cổ Phiếu",
            "⚖️ So Sánh Cổ Phiếu",
            "👁️ Theo Dõi & Cảnh Báo",
            "🔬 Backtest Chiến Lược",
            "💼 Quản Lý Danh Mục",
            "📄 Xuất Báo Cáo PDF",
            "🛰️ Nguồn Dữ Liệu",
        ]
        menu_icons = [
            "bank", "search", "journal-text", "calculator", "folder2-open", "graph-up", "newspaper",
            "star-fill", "funnel", "layout-split", "bell", "cpu", "briefcase", "file-earmark-pdf", "hdd-network",
        ]

        if HAS_OPTION_MENU:
            current_choice = st.session_state.get("nav_page", menu_options[0])
            def_idx = menu_options.index(current_choice) if current_choice in menu_options else 0
            selected_page = option_menu(
                menu_title=None,
                options=menu_options,
                icons=menu_icons,
                default_index=def_idx,
                key=f"app_option_menu_{def_idx}",
                styles={
                    "container": {
                        "padding": "4px!important",
                        "background-color": "#ffffff" if is_light else "#161b22",
                        "border": "1px solid #e2e8f0" if is_light else "1px solid #30363d",
                        "border-radius": "10px",
                    },
                    "icon": {"color": "#0284c7" if is_light else "#58a6ff", "font-size": "14px"},
                    "nav-link": {
                        "font-size": "13px",
                        "text-align": "left",
                        "margin": "2px 0",
                        "padding": "9px 12px",
                        "border-radius": "8px",
                        "color": "#0f172a" if is_light else "#ffffff",
                        "background-color": "transparent",
                        "--hover-color": "#f1f5f9" if is_light else "#21262d",
                    },
                    "nav-link-selected": {
                        "background": "linear-gradient(90deg, #0284c7, #2563eb)" if is_light else "linear-gradient(90deg, #1f6feb, #238636)",
                        "font-weight": "700",
                        "color": "#ffffff",
                    },
                },
            )
        else:
            current_choice = st.session_state.get("nav_page", menu_options[0])
            def_idx = menu_options.index(current_choice) if current_choice in menu_options else 0
            selected_page = st.radio(
                "Điều hướng chức năng:",
                options=menu_options,
                index=def_idx,
                label_visibility="collapsed",
            )

        if selected_page and selected_page != st.session_state.get("nav_page"):
            st.session_state["nav_page"] = selected_page
            st.rerun()

        # System Status & Info
        st.markdown("---")
        st.markdown(f"""
        <div style="font-size:11px; color:{brand_sub}; line-height: 1.6;">
            <div>🟢 <b>Giá:</b> DNSE (gần nhất) + Vnstock/Vietstock (lịch sử)</div>
            <div>📑 <b>BCTC:</b> VCI → KBS → Vietstock → PDF</div>
            <div>⚡ <b>Bộ nhớ đệm:</b> DiskCache + Memory</div>
            <div>🏛️ <b>Cơ sở dữ liệu:</b> DuckDB OLAP</div>
        </div>
        """, unsafe_allow_html=True)

        notice_border = "#f59e0b" if is_light else "#ffab00"
        notice_bg = "#fffbeb" if is_light else "#161b22"
        notice_color = "#92400e" if is_light else "#8b949e"
        st.markdown(f"""
        <div style="margin-top: 20px; padding: 10px; background: {notice_bg}; border-radius: 6px; font-size: 10px; color: {notice_color}; border-left: 3px solid {notice_border};">
            <b>Khuyến cáo học thuật:</b><br>
            Hệ thống phục vụ nghiên cứu & học tập. Các mô hình định lượng không đảm bảo lợi nhuận tương lai.
        </div>
        """, unsafe_allow_html=True)

    return selected_page


def main():
    selected_page = render_sidebar()

    # Route to pages
    try:
        if "Tổng Quan Thị Trường" in selected_page:
            market_overview.render()
        elif "Phân Tích Cổ Phiếu" in selected_page:
            stock_analysis.render()
        elif "Báo Cáo Tài Chính" in selected_page:
            financial_statements.render()
        elif "Chỉ Số Tài Chính" in selected_page:
            financial_ratios.render()
        elif "Tài Liệu" in selected_page:
            documents.render()
        elif "Bộ Lọc" in selected_page:
            screener.render()
        elif "So Sánh" in selected_page:
            compare.render()
        elif "Theo Dõi" in selected_page:
            watchlist.render()
        elif "Nguồn Dữ Liệu" in selected_page:
            data_sources.render()
        elif "Phân Tích Kỹ Thuật" in selected_page:
            technical_analysis.render()
        elif "Tin Tức" in selected_page:
            company_news.render()
        elif "Điểm Cơ Hội Đầu Tư" in selected_page:
            opportunity_score.render()
        elif "Backtest" in selected_page:
            backtest.render()
        elif "Danh Mục" in selected_page:
            portfolio.render()
        elif "Xuất Báo Cáo" in selected_page:
            pdf_report.render()
        else:
            market_overview.render()

    except Exception as exc:
        logger.exception("Lỗi khi render trang %s: %s", selected_page, exc)
        st.error(f"⚠️ Đã xảy ra lỗi khi tải trang: {exc}")
        with st.expander("Chi tiết lỗi kỹ thuật (Debug)"):
            st.exception(exc)


if __name__ == "__main__":
    main()
