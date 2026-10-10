"""
Plotly chart factory for Stock Analytics Pro.

All charts use the dark Plotly template.
No random data – all inputs must come from real DataFrames.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from config.constants import (
    COLOR_BEARISH, COLOR_BULLISH, COLOR_NEUTRAL, PLOTLY_TEMPLATE
)

import streamlit as st

# ─────────────────── Module-level fallback color tokens ──────────────────────
_BG = "#ffffff"
_CARD = "#ffffff"
_GRID = "#f1f5f9"
_TEXT = "#0f172a"
_AXIS = "#64748b"

# ─────────────────── Dynamic Base layout ─────────────────────────────────────
def _get_theme_colors() -> dict:
    try:
        theme = st.session_state.get("theme", "light")
    except Exception:
        theme = "light"

    if theme == "dark":
        return {
            "template": "plotly_dark",
            "bg": "#0d1117",
            "card": "#161b22",
            "grid": "#30363d",
            "text": "#e6edf3",
            "axis": "#8b949e",
            "legend_bg": "rgba(22,27,34,0.8)",
        }
    return {
        "template": "plotly_white",
        "bg": "#ffffff",
        "card": "#ffffff",
        "grid": "#f1f5f9",
        "text": "#0f172a",
        "axis": "#64748b",
        "legend_bg": "rgba(255,255,255,0.9)",
    }


def _base_layout(**kwargs) -> dict:
    colors = _get_theme_colors()
    layout = {
        "template": colors["template"],
        "paper_bgcolor": colors["bg"],
        "plot_bgcolor": colors["card"],
        "font": {"color": colors["text"], "family": "Inter, Roboto, sans-serif", "size": 12},
        "margin": {"l": 60, "r": 20, "t": 50, "b": 40},
        "xaxis": {"gridcolor": colors["grid"], "zerolinecolor": colors["grid"], "tickfont": {"color": colors["axis"]}},
        "yaxis": {"gridcolor": colors["grid"], "zerolinecolor": colors["grid"], "tickfont": {"color": colors["axis"]}},
        "legend": {"bgcolor": colors["legend_bg"], "bordercolor": colors["grid"], "borderwidth": 1},
        "hoverlabel": {"bgcolor": colors["card"], "bordercolor": colors["grid"], "font_color": colors["text"]},
    }
    layout.update(kwargs)
    return layout


# ─────────────────── Candlestick Chart ────────────────────────────────────────

def candlestick_chart(
    df: pd.DataFrame,
    symbol: str = "",
    show_volume: bool = True,
    ma_cols: Optional[List[str]] = None,
    height: int = 600,
) -> go.Figure:
    """
    Full candlestick chart with optional MA overlays and volume.

    Parameters
    ----------
    df       : DataFrame with columns: timestamp/index, open, high, low, close, volume
    symbol   : Title prefix
    show_volume : Attach volume subplot
    ma_cols  : List of MA column names in df to overlay, e.g. ['SMA_20', 'SMA_50']
    """
    if df.empty:
        return _empty_chart("Không có dữ liệu giá")

    # Prepare x-axis
    x_col = "timestamp" if "timestamp" in df.columns else df.index

    row_heights = [0.7, 0.3] if show_volume else [1.0]
    rows = 2 if show_volume else 1
    fig = make_subplots(
        rows=rows, cols=1, shared_xaxes=True,
        row_heights=row_heights,
        vertical_spacing=0.03,
    )

    # ── Candlestick ──
    fig.add_trace(
        go.Candlestick(
            x=df[x_col] if isinstance(x_col, str) else x_col,
            open=df["open"], high=df["high"], low=df["low"], close=df["close"],
            name=symbol,
            increasing_line_color=COLOR_BULLISH, decreasing_line_color=COLOR_BEARISH,
            increasing_fillcolor=COLOR_BULLISH, decreasing_fillcolor=COLOR_BEARISH,
        ),
        row=1, col=1,
    )

    # ── MA overlays ──
    ma_colors = {
        "SMA_10": "#ffffff", "SMA_20": "#2979ff", "SMA_50": "#ff9800",
        "SMA_100": "#e91e63", "SMA_200": "#9c27b0",
        "EMA_12": "#00bcd4", "EMA_26": "#ff5722",
    }
    if ma_cols:
        for col in ma_cols:
            if col in df.columns:
                color = ma_colors.get(col, "#aaaaaa")
                fig.add_trace(
                    go.Scatter(
                        x=df[x_col] if isinstance(x_col, str) else x_col,
                        y=df[col],
                        name=col,
                        line={"color": color, "width": 1.2},
                        hovertemplate=f"{col}: %{{y:,.0f}}<extra></extra>",
                    ),
                    row=1, col=1,
                )

    # ── Volume ──
    if show_volume and "volume" in df.columns:
        colors = [
            COLOR_BULLISH if (c >= o) else COLOR_BEARISH
            for c, o in zip(df["close"].fillna(0), df["open"].fillna(0))
        ]
        fig.add_trace(
            go.Bar(
                x=df[x_col] if isinstance(x_col, str) else x_col,
                y=df["volume"],
                name="Khối lượng",
                marker_color=colors,
                opacity=0.7,
                hovertemplate="KL: %{y:,.0f}<extra></extra>",
            ),
            row=2, col=1,
        )

    layout = _base_layout(
        title={"text": f"📈 Biểu đồ nến – {symbol}", "font_size": 14},
        height=height,
        xaxis_rangeslider_visible=False,
    )
    fig.update_layout(**layout)
    fig.update_yaxes(tickformat=",.0f", row=1, col=1)
    if show_volume:
        fig.update_yaxes(tickformat=",.0f", row=2, col=1, title_text="Khối lượng")
    return fig


# ─────────────────── RSI Chart ────────────────────────────────────────────────

def rsi_chart(df: pd.DataFrame, height: int = 250) -> go.Figure:
    if df.empty or "RSI" not in df.columns:
        return _empty_chart("Chưa tính RSI")
    x = df.get("timestamp", df.index)
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=x, y=df["RSI"], name="RSI",
        line={"color": "#f06292", "width": 1.5},
        hovertemplate="RSI: %{y:.1f}<extra></extra>",
    ))
    for level, color, dash in [(70, COLOR_BEARISH, "dash"), (50, _AXIS, "dot"), (30, COLOR_BULLISH, "dash")]:
        fig.add_hline(y=level, line_dash=dash, line_color=color, opacity=0.6)
    fig.update_layout(**_base_layout(title_text="RSI (14)", height=height))
    fig.update_yaxes(range=[0, 100])
    return fig


# ─────────────────── MACD Chart ──────────────────────────────────────────────

def macd_chart(df: pd.DataFrame, height: int = 250) -> go.Figure:
    if df.empty or "MACD" not in df.columns:
        return _empty_chart("Chưa tính MACD")
    x = df.get("timestamp", df.index)
    fig = go.Figure()

    if "MACD_hist" in df.columns:
        hist = df["MACD_hist"].fillna(0)
        colors = [COLOR_BULLISH if v >= 0 else COLOR_BEARISH for v in hist]
        fig.add_trace(go.Bar(x=x, y=hist, name="Histogram",
                             marker_color=colors, opacity=0.8))

    fig.add_trace(go.Scatter(x=x, y=df["MACD"], name="MACD",
                             line={"color": "#2979ff", "width": 1.5}))
    if "MACD_signal" in df.columns:
        fig.add_trace(go.Scatter(x=x, y=df["MACD_signal"], name="Signal",
                                 line={"color": "#ff9800", "width": 1.5, "dash": "dash"}))
    fig.add_hline(y=0, line_color=_AXIS, line_dash="dot", opacity=0.5)
    fig.update_layout(**_base_layout(title_text="MACD (12,26,9)", height=height))
    return fig


# ─────────────────── Bollinger Bands ─────────────────────────────────────────

def bollinger_chart(df: pd.DataFrame, symbol: str = "", height: int = 350) -> go.Figure:
    required = ["close", "BB_upper", "BB_mid", "BB_lower"]
    if df.empty or not all(c in df.columns for c in required):
        return _empty_chart("Chưa tính Bollinger Bands")
    x = df.get("timestamp", df.index)
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=x, y=df["BB_upper"], name="Upper", line={"color": "#90caf9", "width": 1, "dash": "dot"}))
    fig.add_trace(go.Scatter(x=x, y=df["BB_lower"], name="Lower", line={"color": "#90caf9", "width": 1, "dash": "dot"},
                             fill="tonexty", fillcolor="rgba(41,121,255,0.08)"))
    fig.add_trace(go.Scatter(x=x, y=df["BB_mid"], name="Mid", line={"color": "#2979ff", "width": 1}))
    fig.add_trace(go.Scatter(x=x, y=df["close"], name="Giá", line={"color": COLOR_BULLISH, "width": 1.5}))
    fig.update_layout(**_base_layout(title_text=f"Bollinger Bands – {symbol}", height=height))
    return fig


# ─────────────────── Financial Bar Chart ─────────────────────────────────────

def financial_bar_chart(
    series: pd.Series, title: str = "", unit: str = "Tỷ VND",
    color: str = COLOR_BULLISH, height: int = 300
) -> go.Figure:
    if series is None or series.empty:
        return _empty_chart("Không có dữ liệu tài chính")
    fig = go.Figure(go.Bar(
        x=list(range(len(series))),
        y=series.values / 1e9,
        marker_color=[COLOR_BULLISH if v >= 0 else COLOR_BEARISH for v in series.values],
        hovertemplate=f"%{{y:,.1f}} {unit}<extra></extra>",
    ))
    fig.update_layout(**_base_layout(title_text=title, height=height))
    fig.update_yaxes(title_text=unit)
    return fig


# ─────────────────── Portfolio Pie ────────────────────────────────────────────

def portfolio_pie(df: pd.DataFrame) -> go.Figure:
    if df.empty:
        return _empty_chart("Danh mục trống")
    fig = go.Figure(go.Pie(
        labels=df["symbol"], values=df["current_value"],
        hole=0.4,
        textinfo="label+percent",
        hovertemplate="%{label}: %{value:,.0f} VND<extra></extra>",
    ))
    fig.update_layout(**_base_layout(title_text="Phân bổ danh mục"))
    return fig


# ─────────────────── Line comparison chart ───────────────────────────────────

def line_comparison_chart(
    series_dict: Dict[str, pd.Series],
    title: str = "",
    height: int = 400,
    pct_normalize: bool = True,
) -> go.Figure:
    """Plot multiple series, optionally normalised to 100 at start."""
    if not series_dict:
        return _empty_chart("Không có dữ liệu")
    colors = ["#2979ff", "#00e676", "#ff9800", "#e91e63", "#9c27b0"]
    fig = go.Figure()
    for i, (name, s) in enumerate(series_dict.items()):
        if s is None or s.empty:
            continue
        y = s / s.iloc[0] * 100 if pct_normalize else s
        fig.add_trace(go.Scatter(
            x=s.index, y=y, name=name,
            line={"color": colors[i % len(colors)], "width": 1.8},
            hovertemplate=f"{name}: %{{y:.1f}}<extra></extra>",
        ))
    if pct_normalize:
        fig.add_hline(y=100, line_color=_get_theme_colors()["axis"], line_dash="dot", opacity=0.4)
    fig.update_layout(**_base_layout(title_text=title, height=height))
    return fig


# ─────────────────── Score gauge ─────────────────────────────────────────────

def score_gauge(score: Optional[float], title: str = "Score", height: int = 250) -> go.Figure:
    if score is None:
        return _empty_chart("Chưa có điểm")
    if score >= 80:
        color = COLOR_BULLISH
    elif score >= 65:
        color = "#69f0ae"
    elif score >= 50:
        color = "#ffd740"
    elif score >= 35:
        color = "#ff8f00"
    else:
        color = COLOR_BEARISH

    c = _get_theme_colors()

    fig = go.Figure(go.Indicator(
        mode="gauge+number",
        value=score,
        domain={"x": [0, 1], "y": [0, 1]},
        title={"text": title, "font": {"color": c["text"], "size": 14}},
        number={"font": {"color": color, "size": 36}},
        gauge={
            "axis": {"range": [0, 100], "tickcolor": c["axis"]},
            "bar": {"color": color},
            "bgcolor": c["card"],
            "borderwidth": 1,
            "bordercolor": c["grid"],
            "steps": [
                {"range": [0, 35], "color": "rgba(255,23,68,0.15)"},
                {"range": [35, 50], "color": "rgba(255,143,0,0.15)"},
                {"range": [50, 65], "color": "rgba(255,215,64,0.15)"},
                {"range": [65, 80], "color": "rgba(105,240,174,0.15)"},
                {"range": [80, 100], "color": "rgba(0,230,118,0.2)"},
            ],
        },
    ))
    fig.update_layout(
        paper_bgcolor=c["bg"], font={"color": c["text"], "family": "Inter, sans-serif"},
        height=height, margin={"t": 30, "b": 10, "l": 30, "r": 30},
    )
    return fig


# ─────────────────── Backtest equity curve ───────────────────────────────────

def backtest_equity_curve(portfolio_values: List[Dict], benchmark_df: pd.DataFrame = None) -> go.Figure:
    if not portfolio_values:
        return _empty_chart("Không có dữ liệu backtest")
    df = pd.DataFrame(portfolio_values)
    if "date" in df.columns:
        df["date"] = pd.to_datetime(df["date"])
    fig = go.Figure()
    initial = df["value"].iloc[0]
    fig.add_trace(go.Scatter(
        x=df["date"], y=df["value"] / initial * 100,
        name="Chiến lược", line={"color": "#2979ff", "width": 2},
    ))
    if benchmark_df is not None and not benchmark_df.empty:
        if "timestamp" in benchmark_df.columns:
            benchmark_df = benchmark_df.set_index("timestamp")
        b_init = float(benchmark_df["close"].iloc[0])
        fig.add_trace(go.Scatter(
            x=benchmark_df.index, y=benchmark_df["close"] / b_init * 100,
            name="VN-Index (Buy & Hold)", line={"color": COLOR_NEUTRAL, "width": 1.5, "dash": "dash"},
        ))
    fig.add_hline(y=100, line_color=_AXIS, line_dash="dot", opacity=0.4)
    fig.update_layout(**_base_layout(title_text="Đường vốn Backtest (Chuẩn hóa = 100)", height=400))
    return fig


# ─────────────────── Utility ──────────────────────────────────────────────────

def _empty_chart(message: str) -> go.Figure:
    fig = go.Figure()
    fig.add_annotation(
        text=message, showarrow=False,
        x=0.5, y=0.5, xref="paper", yref="paper",
        font={"size": 14, "color": _AXIS},
    )
    fig.update_layout(**_base_layout(height=300))
    return fig
