"""
Page – Investment Opportunity Score (Chấm điểm cơ hội đầu tư)
"""
import streamlit as st
import pandas as pd

from services.stock_service import StockService
from components.charts import score_gauge
from components.metrics import section_header, warning_box, score_badge, render_score_breakdown
from config.constants import SCORE_CATEGORIES


def render():
    st.markdown("""
    <div class="page-header">
        <h1 style="font-size:22px;font-weight:800;color:#e6edf3;margin:0">
            🎯 Chấm Điểm Cơ Hội Đầu Tư
        </h1>
        <p style="font-size:13px;color:#8b949e;margin:4px 0 0 0">
            Mô hình chấm điểm 0–100 dựa trên quy tắc minh bạch
        </p>
    </div>
    """, unsafe_allow_html=True)

    # Legend
    with st.expander("📋 Phân loại điểm"):
        cols = st.columns(5)
        cats = list(SCORE_CATEGORIES.items())
        for i, ((lo, hi), (label, color, emoji)) in enumerate(cats):
            with cols[i]:
                st.markdown(
                    f'<div style="background:{color}20;border:1px solid {color};border-radius:8px;'
                    f'padding:8px;text-align:center">'
                    f'<div style="font-size:18px">{emoji}</div>'
                    f'<div style="color:{color};font-weight:700">{lo}–{hi}</div>'
                    f'<div style="font-size:12px;opacity:0.9">{label}</div>'
                    f'</div>',
                    unsafe_allow_html=True,
                )

    st.markdown("---")

    col1, col2 = st.columns([2, 1])
    with col1:
        symbol = st.text_input("Mã cổ phiếu", value=st.session_state.get("current_symbol", "FPT"),
                               key="score_symbol").upper().strip()
    with col2:
        st.markdown("<br>", unsafe_allow_html=True)
        run_btn = st.button("🎯 Tính điểm", type="primary", use_container_width=True)

    if not symbol:
        st.info("Nhập mã cổ phiếu để chấm điểm.")
        return

    if run_btn or True:
        with st.spinner(f"Đang tính điểm cho {symbol}..."):
            try:
                svc = StockService(symbol, days=365)
                result = svc.compute_opportunity_score()
            except Exception as e:
                st.error(f"Lỗi: {e}")
                return

        composite = result.get("composite", {})
        sub_scores = result.get("sub_scores", {})
        score = composite.get("score")
        classification = composite.get("classification", {})
        components = composite.get("components", {})
        coverage = composite.get("coverage_pct", 0)

        # ── Main score display ──
        col_gauge, col_detail = st.columns([1, 2])
        with col_gauge:
            st.plotly_chart(score_gauge(score, "Điểm cơ hội"), use_container_width=True)
            if score is not None:
                badge = score_badge(score, classification.get("label", ""))
                st.markdown(badge, unsafe_allow_html=True)
            st.metric("Độ phủ dữ liệu", f"{coverage}%")

        with col_detail:
            section_header("Điểm thành phần")
            weights = {"technical": 25, "momentum": 20, "fundamental": 25, "valuation": 20, "risk": 10}
            labels = {
                "technical": "🔧 Kỹ thuật",
                "momentum": "⚡ Động lượng",
                "fundamental": "📊 Cơ bản",
                "valuation": "💰 Định giá",
                "risk": "⚠️ Rủi ro",
            }
            for key, label in labels.items():
                val = sub_scores.get(key)
                weight = weights.get(key, 0)
                c1, c2, c3 = st.columns([2, 1, 1])
                with c1:
                    st.markdown(f"**{label}**")
                with c2:
                    st.markdown(f"{val:.0f}/100" if val is not None else "N/A")
                with c3:
                    if val is not None:
                        st.progress(val / 100)
                    else:
                        st.caption("Thiếu DL")

        # ── Note / disclaimer ──
        if composite.get("note"):
            st.info(f"📌 {composite['note']}")

        st.caption(composite.get("disclaimer", ""))

        # ── Component breakdown ──
        if components:
            section_header("Chi tiết tính điểm từng nhóm")
            comp_rows = []
            for key, data in components.items():
                comp_rows.append({
                    "Nhóm": key.replace("_", " ").title(),
                    "Trọng số": f"{data.get('weight', 0):.0f}%",
                    "Điểm (0-100)": f"{data.get('score', 'N/A')}",
                    "Đóng góp": f"{data.get('contribution', 'N/A'):.1f}" if data.get('contribution') else "N/A",
                    "Trạng thái": "✅" if data.get("status") == "ok" else "⚠️",
                })
            st.dataframe(pd.DataFrame(comp_rows), use_container_width=True, hide_index=True)

        # ── Formula explanation ──
        with st.expander("📐 Công thức và ngưỡng tính điểm"):
            st.markdown("""
            ### Công thức tổng quát
            ```
            Điểm_composite = Σ (Điểm_nhóm_i × Trọng_số_i) / Tổng_trọng_số_có_dữ_liệu
            ```

            ### Trọng số mặc định
            | Nhóm | Trọng số |
            |------|----------|
            | Kỹ thuật (Technical) | 25% |
            | Động lượng (Momentum) | 20% |
            | Cơ bản (Fundamental) | 25% |
            | Định giá (Valuation) | 20% |
            | Rủi ro (Risk) | 10% |

            ### Xử lý dữ liệu thiếu
            - Nếu một nhóm thiếu dữ liệu → **không gán điểm 0**
            - Điểm được chuẩn hóa trên tổng trọng số có dữ liệu
            - Báo cáo rõ % độ phủ dữ liệu

            ### Lưu ý quan trọng
            > Đây là điểm quy tắc nội bộ, **KHÔNG phải xác suất sinh lời**.
            > Điểm cao không đảm bảo lợi nhuận. Luôn xem xét rủi ro.
            """)
