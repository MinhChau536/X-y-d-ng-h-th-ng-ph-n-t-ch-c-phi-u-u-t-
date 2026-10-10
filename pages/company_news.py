"""
Trang Tin Tức Doanh Nghiệp (Company News & Market Intelligence).
Giao diện đồng bộ chuẩn xác theo thiết kế nền tảng Stockwise.
"""
from __future__ import annotations

from datetime import datetime
import streamlit as st
from services.stock_service import get_repo
import pandas as pd

from services.company_news_service import CompanyNewsService
from services.stock_service import StockService
from data.data_repository import DataRepository

news_service = CompanyNewsService()



def render():
    curr_sym = st.session_state.get("current_symbol", "PNJ").strip().upper()

    # Lấy thông tin lịch sử giá để hiển thị metadata phiên & giai đoạn
    stock_svc = StockService(curr_sym, days=1825)
    price_df = stock_svc.get_price_df()

    start_date_str = "11/10/2018"
    end_date_str = datetime.now().strftime("%d/%m/%Y")
    n_bars = 1993

    if price_df is not None and not price_df.empty:
        n_bars = len(price_df)
        try:
            if "timestamp" in price_df.columns:
                t_series = pd.to_datetime(price_df["timestamp"], errors="coerce").dropna()
            elif "time" in price_df.columns:
                t_series = pd.to_datetime(price_df["time"], errors="coerce").dropna()
            else:
                t_series = pd.to_datetime(price_df.index, errors="coerce").dropna()

            if not t_series.empty:
                start_date_str = t_series.min().strftime("%d/%m/%Y")
                end_date_str = t_series.max().strftime("%d/%m/%Y")
        except Exception:
            pass

    # ── Top Section: 2 Columns (Meta bên trái, Bộ lọc nguồn bên phải) ──
    col_left, col_right = st.columns([1.1, 1.0])

    with col_left:
        st.markdown(f"""
        <div style="padding-top: 4px; line-height: 1.6;">
            <div style="font-size: 14px; font-weight: 700; color: #1e293b; margin-bottom: 3px;">
                Nhóm dữ liệu: <span style="font-weight: 600; color: #334155;">Cổ phiếu doanh nghiệp</span>
            </div>
            <div style="font-size: 13.5px; font-weight: 700; color: #1e293b; margin-bottom: 3px;">
                Dữ liệu giá hiện có: <span style="font-weight: 600; color: #334155;">{n_bars:,} phiên</span>
            </div>
            <div style="font-size: 13.5px; font-weight: 700; color: #1e293b; margin-bottom: 6px;">
                Giai đoạn: <span style="font-weight: 600; color: #334155;">{start_date_str} – {end_date_str}</span>
            </div>
            <div style="font-size: 12px; color: #64748b; font-style: italic;">
                Hồ sơ cơ bản lấy từ danh mục nội bộ; chưa tự suy đoán lĩnh vực kinh doanh.
            </div>
        </div>
        """, unsafe_allow_html=True)

    # Lấy tin tức (có hỗ trợ force refresh)
    force_refresh = st.session_state.get(f"force_refresh_news_{curr_sym}", False)
    if force_refresh:
        st.session_state[f"force_refresh_news_{curr_sym}"] = False

    news_data = news_service.get_company_news(curr_sym, force_refresh=force_refresh)
    all_articles = news_data.get("news", [])
    available_sources = news_data.get("sources", ["CafeF", "VnExpress", "Thanh Niên", "Vietstock", "Tin Nhanh Chứng Khoán"])
    if not available_sources:
        available_sources = ["CafeF", "VnExpress", "Thanh Niên", "Vietstock"]

    # Đảm bảo nguồn mặc định đẹp mắt như trong ảnh
    default_sources = [s for s in ["CafeF", "VnExpress", "Thanh Niên"] if s in available_sources]
    if not default_sources:
        default_sources = available_sources[:3]

    with col_right:
        st.markdown("<p style='font-size: 13px; font-weight: 600; color: #334155; margin-bottom: 4px;'>Chọn nguồn báo</p>", unsafe_allow_html=True)
        selected_sources = st.multiselect(
            "Chọn nguồn báo",
            options=available_sources,
            default=default_sources,
            key=f"news_sources_select_{curr_sym}",
            label_visibility="collapsed",
        )

        c_space, c_btn = st.columns([1, 2])
        with c_btn:
            if st.button("🔄 Làm mới tin tức", key=f"btn_refresh_news_{curr_sym}", use_container_width=True):
                st.session_state[f"force_refresh_news_{curr_sym}"] = True
                st.rerun()

    # Lọc danh sách bài viết theo nguồn đã chọn
    if selected_sources:
        filtered_articles = [a for a in all_articles if a.get("source") in selected_sources]
    else:
        filtered_articles = all_articles

    st.markdown("<div style='height: 18px;'></div>", unsafe_allow_html=True)

    # ── Feed Header ──
    count_found = len(filtered_articles)
    st.markdown(f"""
    <div style="font-size: 12.5px; color: #64748b; margin-bottom: 16px; border-bottom: 1px solid #e2e8f0; padding-bottom: 8px;">
        <b>{count_found} bài liên quan tìm thấy</b> • Sắp xếp theo thời gian đăng (mới nhất trước)
    </div>
    """, unsafe_allow_html=True)

    # ── News Feed Items (Render theo đúng format mẫu ảnh) ──
    if not filtered_articles:
        st.info(f"Không tìm thấy bài viết nào từ các nguồn báo đã chọn cho mã {curr_sym}. Vui lòng thử chọn thêm nguồn báo khác.")
        return

    for item in filtered_articles:
        title = item.get("title", "")
        source = item.get("source", "Báo chí")
        date_str = item.get("date", datetime.now().strftime("%d/%m/%Y %H:%M"))
        url = item.get("url") or "#"
        summary = item.get("summary") or ""
        sentiment = item.get("sentiment", "neutral")

        # Màu sắc tag cảm xúc
        if sentiment == "positive":
            tag_color = "#16a34a"
            tag_bg = "#f0fdf4"
            tag_text = "Tích cực"
        elif sentiment == "negative":
            tag_color = "#dc2626"
            tag_bg = "#fef2f2"
            tag_text = "Tiêu cực"
        else:
            tag_color = "#475569"
            tag_bg = "#f8fafc"
            tag_text = "Trung tính"

        st.markdown(f"""
        <div style="margin-bottom: 18px; padding-bottom: 12px; border-bottom: 1px solid #f1f5f9;">
            <div style="margin-bottom: 4px;">
                <a href="{url}" target="_blank" rel="noopener noreferrer" 
                   style="color: #0369a1; font-size: 15px; font-weight: 700; text-decoration: none; line-height: 1.4;">
                    {title}
                </a>
            </div>
            <div style="font-size: 12px; color: #64748b; display: flex; align-items: center; gap: 8px; flex-wrap: wrap;">
                <span>{source}</span>
                <span>•</span>
                <span>{date_str}</span>
                <span>•</span>
                <a href="{url}" target="_blank" rel="noopener noreferrer" 
                   style="color: #64748b; text-decoration: none; font-weight: 500;">
                    Mở bài gốc ↗
                </a>
                <span style="margin-left: 6px; padding: 1px 7px; background: {tag_bg}; color: {tag_color}; border-radius: 4px; font-size: 11px; font-weight: 600;">
                    {tag_text}
                </span>
            </div>
            {f'<div style="font-size: 12.5px; color: #475569; margin-top: 5px; line-height: 1.5;">{summary[:260]}...</div>' if len(summary) > 20 else ''}
        </div>
        """, unsafe_allow_html=True)
