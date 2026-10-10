"""Tiện ích giao diện dùng chung cho các trang mới."""
from __future__ import annotations

from typing import Dict, Iterable, List, Optional

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from components.charts import _base_layout, _empty_chart

PALETTE = ["#2563eb", "#16a34a", "#ea580c", "#9333ea", "#0891b2", "#dc2626"]


def page_header(title: str, subtitle: str = ""):
    is_light = st.session_state.get("theme", "light") == "light"
    st.markdown(f"""
    <div class="page-header">
        <h1 style="font-size:22px;font-weight:800;color:{'#0f172a' if is_light else '#e6edf3'};margin:0">{title}</h1>
        <p style="font-size:13px;color:{'#475569' if is_light else '#8b949e'};margin:4px 0 0 0">{subtitle}</p>
    </div>
    """, unsafe_allow_html=True)


def symbol_input(key: str, label: str = "Mã cổ phiếu") -> str:
    """Ô nhập mã đồng bộ với mã đang chọn ở thanh bên."""
    sym = st.text_input(label, value=st.session_state.get("current_symbol", "FPT"), key=key).upper().strip()
    if sym and sym != st.session_state.get("current_symbol"):
        st.session_state["current_symbol"] = sym
    return sym


def fmt_num(v, d: int = 0, suffix: str = "") -> str:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return "–"
    try:
        return f"{float(v):,.{d}f}{suffix}"
    except (TypeError, ValueError):
        return str(v)


def fmt_bil(v) -> str:
    return fmt_num(v / 1e9 if v is not None and pd.notna(v) else None, 0)


def bar_chart(x: List, series: Dict[str, Iterable], title: str = "", unit: str = "", height: int = 320,
              barmode: str = "group") -> go.Figure:
    if not x:
        return _empty_chart("Không có dữ liệu")
    fig = go.Figure()
    for i, (name, ys) in enumerate(series.items()):
        fig.add_trace(go.Bar(x=x, y=list(ys), name=name, marker_color=PALETTE[i % len(PALETTE)],
                             hovertemplate=f"{name}: %{{y:,.2f}} {unit}<extra></extra>"))
    fig.update_layout(**_base_layout(title_text=title, height=height, barmode=barmode))
    if unit:
        fig.update_yaxes(title_text=unit)
    return fig


def line_chart(x: List, series: Dict[str, Iterable], title: str = "", unit: str = "", height: int = 320) -> go.Figure:
    if not x:
        return _empty_chart("Không có dữ liệu")
    fig = go.Figure()
    for i, (name, ys) in enumerate(series.items()):
        fig.add_trace(go.Scatter(x=x, y=list(ys), name=name, mode="lines+markers",
                                 line={"color": PALETTE[i % len(PALETTE)], "width": 2},
                                 hovertemplate=f"{name}: %{{y:,.2f}} {unit}<extra></extra>"))
    fig.update_layout(**_base_layout(title_text=title, height=height))
    if unit:
        fig.update_yaxes(title_text=unit)
    return fig


def source_caption(text: str):
    st.caption(f"🛰️ {text}")


def unique_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Đổi tên cột trùng (vd '2018', '2018' → '2018', '2018 (2)') để Streamlit/Excel hiển thị được."""
    if df is None or df.empty or not df.columns.duplicated().any():
        return df
    seen: Dict[str, int] = {}
    cols = []
    for c in map(str, df.columns):
        seen[c] = seen.get(c, 0) + 1
        cols.append(c if seen[c] == 1 else f"{c} ({seen[c]})")
    out = df.copy()
    out.columns = cols
    return out
