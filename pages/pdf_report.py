"""
Page – PDF Report Generator
"""
import streamlit as st
from datetime import datetime
from pathlib import Path

from services.stock_service import StockService
from data.database import Database
from components.metrics import section_header, warning_box

db = Database()


def render():
    st.markdown("""
    <div class="page-header">
        <h1 style="font-size:22px;font-weight:800;color:#e6edf3;margin:0">
            📄 Tạo Báo Cáo Phân Tích PDF
        </h1>
        <p style="font-size:13px;color:#8b949e;margin:4px 0 0 0">
            Xuất báo cáo theo phong cách công ty chứng khoán chuyên nghiệp
        </p>
    </div>
    """, unsafe_allow_html=True)

    col1, col2, col3 = st.columns(3)
    with col1:
        symbol = st.text_input("Mã cổ phiếu", value=st.session_state.get("current_symbol", "FPT"),
                               key="pdf_symbol").upper().strip()
    with col2:
        report_type = st.selectbox("Loại báo cáo", ["full", "short"],
                                    format_func=lambda x: "Báo cáo đầy đủ" if x == "full" else "Báo cáo ngắn")
    with col3:
        days = st.selectbox("Khoảng thời gian phân tích", [90, 180, 365, 730], index=2,
                             format_func=lambda d: f"{d} ngày ({d//365} năm)" if d >= 365 else f"{d} ngày")

    # Chọn mục theo nhu cầu (có tác dụng thật khi tạo PDF)
    from reports.pdf_generator import PDFReportGenerator as _G
    default = _G.DEFAULT_SECTIONS if report_type == "full" else ["summary", "technical", "scoring"]
    c_a, c_b = st.columns([3, 1])
    with c_a:
        sections = st.multiselect("📋 Các mục cần xuất", list(_G.SECTIONS), default=default,
                                  format_func=_G.SECTIONS.get)
    with c_b:
        fin_period = st.selectbox("Kỳ BCTC", ["year", "quarter"], format_func=lambda p: "Năm" if p == "year" else "Quý (TTM)")
    include_news = st.checkbox("Kèm tin tức doanh nghiệp mới nhất", value=True)

    if not symbol:
        st.info("Nhập mã cổ phiếu để tạo báo cáo.")
        return

    generate_btn = st.button(
        f"📄 TẠO BÁO CÁO PDF – {symbol}",
        type="primary",
        use_container_width=True,
    )

    if generate_btn:
        with st.spinner(f"Đang thu thập dữ liệu và tạo báo cáo cho {symbol}..."):
            try:
                # Run full analysis
                svc = StockService(symbol, days=days, fin_period=fin_period)
                analysis = svc.full_analysis()

                # Tin tức thật cho mục "Bối cảnh & Tin tức" (không có thì PDF ghi rõ là chưa thu thập được)
                analysis["news"] = []
                if include_news:
                    try:
                        from services.company_news_service import CompanyNewsService
                        analysis["news"] = CompanyNewsService().get_company_news(symbol).get("news", [])
                    except Exception:
                        pass

                # Generate PDF
                from reports.pdf_generator import PDFReportGenerator
                generator = PDFReportGenerator()
                pdf_bytes = generator.generate(analysis, report_type=report_type, sections=sections)

                # Log to DB
                ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = f"{symbol}_{report_type}_{ts}.pdf"
                db.log_report(symbol, report_type, filename)

                st.success(f"✅ Báo cáo đã tạo thành công! ({len(pdf_bytes):,} bytes)")

                # Download button
                st.download_button(
                    label=f"⬇️ Tải báo cáo {symbol}.pdf",
                    data=pdf_bytes,
                    file_name=filename,
                    mime="application/pdf",
                    type="primary",
                )

                # Preview summary
                section_header("Tóm tắt báo cáo")
                opp = analysis.get("opportunity_score", {})
                composite = opp.get("composite", {})
                score = composite.get("score")
                if score is not None:
                    st.metric("Điểm cơ hội đầu tư", f"{score}/100",
                              delta=composite.get("classification", {}).get("label", ""))

                company = analysis.get("company_info", {})
                col1, col2 = st.columns(2)
                with col1:
                    st.markdown("**Thông tin doanh nghiệp:**")
                    st.write(f"Tên: {company.get('company_name', company.get('name', 'N/A'))}")
                    st.write(f"Sàn: {company.get('exchange', 'N/A')}")
                    st.write(f"Ngành: {company.get('sector', 'N/A')}")
                with col2:
                    current = analysis.get("current_price", {})
                    if current and current.get("price"):
                        st.markdown("**Giá tham chiếu:**")
                        st.write(f"{current['price']:,.0f} VND")
                        st.write(f"Nguồn: {current.get('source', 'N/A')}")
                        st.write(f"Thời điểm: {current.get('timestamp', 'N/A')}")

            except ImportError as e:
                st.error(f"❌ Thiếu thư viện: {e}. Chạy: `pip install -r requirements.txt`")
            except Exception as e:
                st.error(f"❌ Lỗi tạo báo cáo: {e}")
                import traceback
                with st.expander("Chi tiết lỗi"):
                    st.code(traceback.format_exc())

    # ── Report history ──
    st.markdown("---")
    section_header("Lịch sử báo cáo")
    history_df = db.get_reports_history(limit=20)
    if not history_df.empty:
        st.dataframe(history_df, use_container_width=True, hide_index=True)
    else:
        st.caption("Chưa có báo cáo nào được tạo.")
