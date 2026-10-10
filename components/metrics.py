"""
Reusable Streamlit UI components / widgets.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

import pandas as pd
import streamlit as st

from config.constants import COLOR_BEARISH, COLOR_BULLISH, COLOR_NEUTRAL


def metric_card(label: str, value: str, delta: Optional[str] = None,
                delta_color: str = "normal", icon: str = ""):
    """Styled metric card using st.metric with icon prefix."""
    display_label = f"{icon} {label}" if icon else label
    st.metric(label=display_label, value=value, delta=delta, delta_color=delta_color)


def score_badge(score: Optional[float], label: str = "") -> str:
    """Return HTML badge string for a score."""
    try:
        is_light = st.session_state.get("theme", "light") == "light"
    except Exception:
        is_light = True

    if score is None:
        bg = "#f1f5f9" if is_light else "#30363d"
        fg = "#64748b" if is_light else "#8b949e"
        return f'<span style="background:{bg};color:{fg};padding:3px 10px;border-radius:12px;font-size:13px">N/A</span>'
    
    if is_light:
        if score >= 80:
            bg, fg = "#dcfce7", "#15803d"
        elif score >= 65:
            bg, fg = "#ecfdf5", "#16a34a"
        elif score >= 50:
            bg, fg = "#fef9c3", "#854d0e"
        elif score >= 35:
            bg, fg = "#ffedd5", "#c2410c"
        else:
            bg, fg = "#fee2e2", "#b91c1c"
    else:
        if score >= 80:
            bg, fg = "#1a472a", "#00e676"
        elif score >= 65:
            bg, fg = "#0d3321", "#69f0ae"
        elif score >= 50:
            bg, fg = "#3d2c00", "#ffd740"
        elif score >= 35:
            bg, fg = "#3d1a00", "#ff8f00"
        else:
            bg, fg = "#3d0014", "#ff1744"

    return (
        f'<span style="background:{bg};color:{fg};padding:4px 12px;'
        f'border-radius:12px;font-size:14px;font-weight:600">'
        f'{score:.0f} – {label}</span>'
    )


def data_status_badge(source: str, timestamp: str, color: str = "#0284c7") -> None:
    """Display data source and freshness."""
    try:
        is_light = st.session_state.get("theme", "light") == "light"
    except Exception:
        is_light = True
    txt_color = "#64748b" if is_light else "#8b949e"
    st.markdown(
        f'<div style="font-size:11px;color:{txt_color};margin-bottom:6px">'
        f'📡 Nguồn: <b style="color:{color}">{source}</b> &nbsp;|&nbsp; '
        f'⏱ Cập nhật: <b>{timestamp}</b></div>',
        unsafe_allow_html=True,
    )


def warning_box(message: str):
    """Display a styled warning."""
    st.warning(f"⚠️ {message}")


def info_box(message: str):
    st.info(f"ℹ️ {message}")


def error_box(message: str):
    st.error(f"❌ {message}")


def section_header(title: str, subtitle: str = ""):
    """Render a styled section header."""
    try:
        is_light = st.session_state.get("theme", "light") == "light"
    except Exception:
        is_light = True
    title_color = "#0f172a" if is_light else "#e6edf3"
    sub_color = "#475569" if is_light else "#8b949e"
    accent = "#0284c7" if is_light else "#2979ff"
    st.markdown(f"""
    <div style="border-left:3px solid {accent};padding-left:12px;margin:16px 0 8px 0">
        <span style="font-size:18px;font-weight:700;color:{title_color}">{title}</span>
        {"<br><span style='font-size:12px;color:" + sub_color + "'>" + subtitle + "</span>" if subtitle else ""}
    </div>
    """, unsafe_allow_html=True)


def render_score_breakdown(components: Dict[str, Any]):
    """Render score component table."""
    rows = []
    for group, data in components.items():
        score = data.get("score")
        max_pts = data.get("max", 100)
        status = data.get("status", "ok")
        reason = data.get("reason", "")
        row = {
            "Nhóm": group.replace("_", " ").title(),
            "Điểm": f"{score:.0f} / {max_pts}" if score is not None else "N/A",
            "Trạng thái": "✅" if status == "ok" else "⚠️ Thiếu dữ liệu",
            "Ghi chú": reason,
        }
        rows.append(row)
    if rows:
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)


def render_signal_row(signals: Dict[str, Any]):
    """Render signal indicators in a row."""
    cols = st.columns(len(signals))
    for i, (name, data) in enumerate(signals.items()):
        if not isinstance(data, dict):
            continue
        signal = data.get("signal", data.get("name", "N/A"))
        color = data.get("color", COLOR_NEUTRAL)
        with cols[i]:
            st.markdown(
                f'<div style="background:#161b22;border-radius:8px;padding:10px;text-align:center">'
                f'<div style="font-size:11px;color:#8b949e">{name.upper()}</div>'
                f'<div style="font-size:13px;font-weight:600;color:{color}">{signal}</div>'
                f'</div>',
                unsafe_allow_html=True,
            )


def pct_color(val: Optional[float]) -> str:
    """Return colored string for a percentage change."""
    if val is None:
        return "N/A"
    color = COLOR_BULLISH if val >= 0 else COLOR_BEARISH
    sign = "+" if val >= 0 else ""
    return f'<span style="color:{color}">{sign}{val:.2f}%</span>'


def format_vnd(val: Optional[float], unit: str = "tỷ") -> str:
    """Format VND value with unit."""
    if val is None or pd.isna(val):
        return "N/A"
    if unit == "tỷ":
        return f"{val / 1e9:,.1f} tỷ"
    if unit == "triệu":
        return f"{val / 1e6:,.1f} triệu"
    return f"{val:,.0f}"


def render_company_header(info: Dict[str, Any], current_price: Optional[Dict] = None):
    """Render company name, exchange, sector and price."""
    symbol = info.get("symbol", "")
    name = info.get("company_name", info.get("short_name", info.get("name", symbol)))
    exchange = info.get("exchange", "")
    sector = info.get("sector", "")

    price_str = "N/A"
    change_str = ""
    if current_price and current_price.get("price"):
        p = current_price["price"]
        p_vnd = p * 1000 if (0 < p < 1000) else p
        price_str = f"{p_vnd:,.0f}"
        chg = current_price.get("change")
        chg_pct = current_price.get("change_pct")
        if chg is not None and chg_pct is not None:
            chg_vnd = chg * 1000 if (0 < abs(chg) < 1000 and 0 < p < 1000) else chg
            color = COLOR_BULLISH if chg >= 0 else COLOR_BEARISH
            sign = "+" if chg >= 0 else ""
            change_str = f'<span style="color:{color};font-size:16px"> {sign}{chg_vnd:,.0f} ({sign}{chg_pct:.2f}%)</span>'

    st.markdown(f"""
    <div style="background:#161b22;border-radius:12px;padding:20px 24px;margin-bottom:16px">
        <div style="font-size:26px;font-weight:800;color:#e6edf3">
            {symbol}
            <span style="font-size:14px;background:#21262d;color:#8b949e;padding:3px 10px;border-radius:8px;margin-left:10px">{exchange}</span>
        </div>
        <div style="font-size:15px;color:#8b949e;margin-top:4px">{name}</div>
        <div style="font-size:12px;color:#58a6ff;margin-top:2px">{sector}</div>
        <div style="font-size:30px;font-weight:700;color:#e6edf3;margin-top:12px">
            {price_str} VND{change_str}
        </div>
    </div>
    """, unsafe_allow_html=True)
