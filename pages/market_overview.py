"""
Trang 1 – Tổng quan thị trường (giao diện kiểu bảng điều khiển chuyên nghiệp).

Bố cục:
  1. Tiêu đề + trạng thái nguồn dữ liệu + nút làm mới
  2. Thẻ 4 chỉ số (VN-Index, VN30, HNX, UPCoM) kèm sparkline 60 phiên
  3. Biểu đồ nến chỉ số + MA20/MA50 + khối lượng  |  Điểm sức khỏe thị trường
  4. Độ rộng thị trường (tăng/giảm/đứng, A/D, % trên MA20, đỉnh/đáy 20 phiên, GTGD)
  5. Bản đồ nhiệt theo ngành (treemap)  |  Hiệu suất ngành
  6. Top cổ phiếu: tăng mạnh / giảm mạnh / giá trị giao dịch / đột biến khối lượng
  7. So sánh hiệu suất + bảng lợi nhuận theo kỳ

Mọi con số đều tính từ dữ liệu giá thật (DNSE → vnstock → Vietstock); thiếu dữ liệu thì hiển thị "—".
"""
from __future__ import annotations

import html
import itertools
from datetime import datetime
from typing import Dict, List, Optional

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

from components.charts import _base_layout, line_comparison_chart
from services import market_service as ms
from services.stock_service import get_repo

INDEX_ORDER = ["VNINDEX", "VN30", "HNX", "UPCOM"]
PERIODS = {"1Th": 31, "3Th": 92, "6Th": 183, "1N": 365, "3N": 1095}
SHORT_IDX = {"VNINDEX": "VNI", "VN30": "VN30", "HNX": "HNX", "UPCOM": "UPCoM"}
_uid = itertools.count()


# ─────────────────────────── Bảng màu theo giao diện ──────────────────────────
def _pal() -> Dict[str, str]:
    dark = st.session_state.get("theme", "light") == "dark"
    if dark:
        return dict(dark=True, text="#e6edf3", muted="#8b949e", card="rgba(22,27,34,0.78)",
                    border="rgba(48,54,61,0.95)", up="#22c55e", down="#f43f5e", ref="#f59e0b",
                    accent="#58a6ff", soft="rgba(255,255,255,0.04)", track="rgba(255,255,255,0.08)")
    return dict(dark=False, text="#0f172a", muted="#64748b", card="rgba(255,255,255,0.82)",
                border="rgba(226,232,240,0.95)", up="#16a34a", down="#dc2626", ref="#d97706",
                accent="#2563eb", soft="rgba(15,23,42,0.03)", track="rgba(15,23,42,0.07)")


def _color(v: Optional[float], p: Dict[str, str]) -> str:
    if v is None or pd.isna(v):
        return p["muted"]
    return p["up"] if v > 0.0001 else p["down"] if v < -0.0001 else p["ref"]


def _f(v, d: int = 2, suffix: str = "", sign: bool = False) -> str:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return "—"
    s = f"{v:+,.{d}f}" if sign else f"{v:,.{d}f}"
    return s + suffix


def _arrow(v: Optional[float]) -> str:
    if v is None or pd.isna(v):
        return ""
    return "▲" if v > 0.0001 else "▼" if v < -0.0001 else "■"


def _css(p: Dict[str, str]) -> str:
    return f"""<style>
.mo-head{{display:flex;justify-content:space-between;align-items:flex-end;flex-wrap:wrap;gap:10px;margin:0 0 14px}}
.mo-title{{font-size:24px;font-weight:800;color:{p['text']};margin:0;letter-spacing:-.3px}}
.mo-sub{{font-size:13px;color:{p['muted']};margin-top:2px}}
.mo-pills{{display:flex;gap:6px;flex-wrap:wrap}}
.mo-pill{{font-size:11.5px;font-weight:600;padding:4px 10px;border-radius:999px;border:1px solid {p['border']};
  background:{p['card']};color:{p['muted']};display:inline-flex;align-items:center;gap:6px}}
.mo-dot{{width:7px;height:7px;border-radius:50%;display:inline-block}}
.mo-card{{background:{p['card']};border:1px solid {p['border']};border-radius:14px;padding:14px 16px;
  backdrop-filter:blur(10px);-webkit-backdrop-filter:blur(10px);transition:transform .18s, box-shadow .18s;height:100%}}
.mo-card:hover{{transform:translateY(-2px);box-shadow:0 10px 28px rgba(15,23,42,{0.35 if p['dark'] else 0.10})}}
.mo-lbl{{font-size:11px;font-weight:700;letter-spacing:.6px;text-transform:uppercase;color:{p['muted']}}}
.mo-val{{font-size:26px;font-weight:800;color:{p['text']};line-height:1.15;margin-top:4px;font-variant-numeric:tabular-nums}}
.mo-chg{{font-size:13px;font-weight:700;font-variant-numeric:tabular-nums}}
.mo-meta{{display:flex;justify-content:space-between;font-size:11px;color:{p['muted']};margin-top:6px;font-variant-numeric:tabular-nums}}
.mo-sec{{display:flex;align-items:baseline;gap:10px;margin:22px 0 10px}}
.mo-sec h3{{font-size:16px;font-weight:800;color:{p['text']};margin:0;padding:0}}
.mo-sec span{{font-size:12px;color:{p['muted']}}}
.mo-kpi{{background:{p['card']};border:1px solid {p['border']};border-radius:12px;padding:10px 12px;height:100%}}
.mo-kpi b{{display:block;font-size:20px;font-weight:800;color:{p['text']};font-variant-numeric:tabular-nums}}
.mo-kpi small{{font-size:11px;color:{p['muted']};font-weight:600}}
.mo-bar{{display:flex;height:12px;border-radius:999px;overflow:hidden;background:{p['track']};margin:8px 0 6px}}
.mo-legend{{display:flex;justify-content:space-between;font-size:12px;font-weight:700;font-variant-numeric:tabular-nums}}
table.mo-t{{width:100%;border-collapse:collapse;font-size:13px;font-variant-numeric:tabular-nums}}
table.mo-t th{{text-align:right;font-size:11px;text-transform:uppercase;letter-spacing:.4px;color:{p['muted']};
  font-weight:700;padding:8px 10px;border-bottom:1px solid {p['border']}}}
table.mo-t th:first-child,table.mo-t td:first-child,table.mo-t th:nth-child(2),table.mo-t td:nth-child(2){{text-align:left}}
table.mo-r th:nth-child(2),table.mo-r td:nth-child(2){{text-align:right}}
table.mo-t td{{text-align:right;padding:7px 8px;border-bottom:1px solid {p['track']};color:{p['text']}}}
table.mo-t tr:hover td{{background:{p['soft']}}}
.mo-sym{{font-weight:800;color:{p['accent']}}}
.mo-badge{{display:inline-block;min-width:66px;text-align:center;padding:3px 8px;border-radius:7px;font-weight:700;color:#fff}}
.mo-comp{{display:flex;justify-content:space-between;font-size:12px;color:{p['muted']};margin:7px 0 3px}}
.mo-comp b{{color:{p['text']}}}
.mo-track{{height:6px;border-radius:999px;background:{p['track']};overflow:hidden}}
.mo-track i{{display:block;height:100%;border-radius:999px}}
html body div[data-testid="stButtonGroup"] button{{background:{p['card']} !important;border-color:{p['border']} !important}}
html body div[data-testid="stButtonGroup"] button p,html body div[data-testid="stButtonGroup"] button span{{color:{p['muted']} !important}}
html body div[data-testid="stButtonGroup"] button[aria-checked="true"]{{background:{p['accent']} !important;border-color:{p['accent']} !important}}
html body div[data-testid="stButtonGroup"] button[aria-checked="true"] p,
html body div[data-testid="stButtonGroup"] button[aria-checked="true"] span{{color:#ffffff !important;font-weight:700 !important}}
.mo-foot{{font-size:11.5px;color:{p['muted']};margin-top:18px}}
</style>"""


def _md(s: str):
    # Gộp thành một dòng để Markdown không hiểu nhầm phần thụt lề là khối code
    st.markdown(" ".join(line.strip() for line in s.splitlines()), unsafe_allow_html=True)


def _section(title: str, sub: str = ""):
    _md(f'<div class="mo-sec"><h3>{title}</h3><span>{sub}</span></div>')


def _spark(values: List[float], color: str, w: int = 170, h: int = 44, fill: bool = True) -> str:
    vals = [float(v) for v in values if v is not None and not pd.isna(v)]
    if len(vals) < 2:
        return f'<svg width="{w}" height="{h}"></svg>'
    lo, hi = min(vals), max(vals)
    rng = (hi - lo) or 1.0
    step = w / (len(vals) - 1)
    pts = [(i * step, h - 3 - (v - lo) / rng * (h - 6)) for i, v in enumerate(vals)]
    line = " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
    gid = f"g{next(_uid)}"
    area = (f'<path d="M0,{h} L{line.replace(" ", " L")} L{w},{h} Z" fill="url(#{gid})"/>' if fill else "")
    return (f'<svg width="100%" height="{h}" viewBox="0 0 {w} {h}" preserveAspectRatio="none">'
            f'<defs><linearGradient id="{gid}" x1="0" x2="0" y1="0" y2="1">'
            f'<stop offset="0%" stop-color="{color}" stop-opacity=".35"/>'
            f'<stop offset="100%" stop-color="{color}" stop-opacity="0"/></linearGradient></defs>'
            f'{area}<polyline points="{line}" fill="none" stroke="{color}" stroke-width="1.8" '
            f'stroke-linejoin="round" stroke-linecap="round" vector-effect="non-scaling-stroke"/></svg>')


# ─────────────────────────── Tải dữ liệu (có cache) ───────────────────────────
@st.cache_data(ttl=300, show_spinner=False)
def _idx(code: str, days: int) -> pd.DataFrame:
    return ms.index_history(code, days=days)


@st.cache_data(ttl=300, show_spinner=False)
def _snapshot(symbols: tuple) -> pd.DataFrame:
    return ms.universe_snapshot(list(symbols))


@st.cache_data(ttl=300, show_spinner=False)
def _stock(sym: str, days: int) -> pd.DataFrame:
    try:
        return get_repo().get_price_history(sym, days=days)
    except Exception:
        return pd.DataFrame()


@st.cache_data(ttl=600, show_spinner=False)
def _status() -> Dict:
    try:
        return get_repo().get_provider_status()
    except Exception as exc:
        return {"error": str(exc)}


def _clear_cache():
    for fn in (_idx, _snapshot, _stock, _status):
        fn.clear()


# ─────────────────────────── Biểu đồ ──────────────────────────────────────────
def _index_chart(df: pd.DataFrame, name: str, kind: str, p: Dict[str, str], height: int = 470) -> go.Figure:
    d = df.copy()
    d["MA20"] = d["close"].rolling(20).mean()
    d["MA50"] = d["close"].rolling(50).mean()
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, row_heights=[0.76, 0.24], vertical_spacing=0.02)
    x = d["timestamp"]
    if kind == "Nến":
        fig.add_trace(go.Candlestick(x=x, open=d["open"], high=d["high"], low=d["low"], close=d["close"], name=name,
                                     increasing_line_color=p["up"], decreasing_line_color=p["down"],
                                     increasing_fillcolor=p["up"], decreasing_fillcolor=p["down"]), 1, 1)
    else:
        col = p["up"] if d["close"].iloc[-1] >= d["close"].iloc[0] else p["down"]
        fig.add_trace(go.Scatter(x=x, y=d["close"], name=name, line=dict(color=col, width=2),
                                 hovertemplate="%{x|%d/%m/%Y}<br>%{y:,.2f}<extra></extra>"), 1, 1)
        lo = float(d["low"].min() if "low" in d else d["close"].min())
        fig.update_yaxes(range=[lo * 0.98, float(d["high"].max() if "high" in d else d["close"].max()) * 1.01], row=1, col=1)
    for ma, c in (("MA20", "#f59e0b"), ("MA50", "#8b5cf6")):
        fig.add_trace(go.Scatter(x=x, y=d[ma], name=ma, line=dict(color=c, width=1.3),
                                 hovertemplate=f"{ma}: %{{y:,.2f}}<extra></extra>"), 1, 1)
    if "volume" in d.columns:
        vc = [p["up"] if c >= o else p["down"] for c, o in zip(d["close"], d["open"].fillna(d["close"]))]
        fig.add_trace(go.Bar(x=x, y=d["volume"], marker_color=vc, opacity=0.55, name="Khối lượng",
                             hovertemplate="KL: %{y:,.0f}<extra></extra>"), 2, 1)
    last = float(d["close"].iloc[-1])
    fig.add_hline(y=last, line=dict(color=p["accent"], width=1, dash="dot"), row=1, col=1,
                  annotation_text=f" {last:,.2f}", annotation_position="right",
                  annotation_font=dict(color=p["accent"], size=11))
    lay = _base_layout(height=height)
    lay.update(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", showlegend=True,
               legend=dict(orientation="h", y=1.04, x=0, bgcolor="rgba(0,0,0,0)", font=dict(size=11)),
               margin=dict(l=8, r=60, t=30, b=8), xaxis_rangeslider_visible=False, hovermode="x unified")
    fig.update_layout(**lay)
    fig.update_xaxes(rangebreaks=[dict(bounds=["sat", "mon"])], showgrid=False)
    fig.update_yaxes(tickformat=",.0f", gridcolor=p["track"], row=1, col=1)
    fig.update_yaxes(tickformat=".2s", gridcolor=p["track"], row=2, col=1)
    return fig


def _treemap(snap: pd.DataFrame, p: Dict[str, str]) -> go.Figure:
    d = snap.copy()
    d["size"] = d["value_bn"].clip(lower=0.05)
    d["label"] = d["symbol"]
    fig = px.treemap(d, path=[px.Constant("Thị trường"), "sector", "label"], values="size", color="change_pct",
                     color_continuous_scale=[[0, "#b91c1c"], [0.35, "#ef4444"], [0.5, "#eab308"],
                                             [0.65, "#22c55e"], [1, "#15803d"]],
                     range_color=[-5, 5], color_continuous_midpoint=0,
                     custom_data=["change_pct", "close", "value_bn"])
    fig.update_traces(
        texttemplate="<b>%{label}</b><br>%{customdata[0]:+.2f}%", textposition="middle center",
        hovertemplate="<b>%{label}</b><br>Thay đổi: %{customdata[0]:+.2f}%<br>Giá: %{customdata[1]:,.0f}"
                      "<br>GTGD: %{customdata[2]:,.1f} tỷ<extra></extra>",
        marker=dict(line=dict(width=1.5, color="rgba(0,0,0,0.25)" if p["dark"] else "#ffffff")),
        root_color="rgba(0,0,0,0)", tiling=dict(pad=2), insidetextfont=dict(color="#ffffff", size=13))
    lay = _base_layout(height=440)
    lay.update(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", margin=dict(l=0, r=0, t=6, b=0),
               coloraxis_colorbar=dict(title="%", thickness=10, len=0.8, ticksuffix="%"))
    fig.update_layout(**lay)
    return fig


def _sector_bars(sec: pd.DataFrame, col: str, p: Dict[str, str]) -> go.Figure:
    d = sec.dropna(subset=[col]).sort_values(col)
    names = [s.split(" ", 1)[1] if " " in s and not s[0].isalnum() else s for s in d["sector"]]
    fig = go.Figure(go.Bar(
        x=d[col], y=names, orientation="h", marker_color=[_color(v, p) for v in d[col]],
        text=[f"{v:+.2f}%" for v in d[col]], textposition="outside", cliponaxis=False,
        customdata=d[["n", "adv", "dec"]].values,
        hovertemplate="<b>%{y}</b><br>%{x:+.2f}%<br>%{customdata[0]} mã · %{customdata[1]} tăng / "
                      "%{customdata[2]} giảm<extra></extra>"))
    lay = _base_layout(height=max(300, 34 * len(d) + 60))
    lay.update(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", showlegend=False,
               margin=dict(l=8, r=50, t=6, b=8))
    fig.update_layout(**lay)
    lo, hi = min(0.0, float(d[col].min())), max(0.0, float(d[col].max()))
    pad = (hi - lo) * 0.35 + 0.3
    fig.update_xaxes(ticksuffix="%", zeroline=True, zerolinecolor=p["muted"], gridcolor=p["track"],
                     range=[lo - (pad if lo < 0 else 0.15), hi + (pad if hi > 0 else 0.15)])
    fig.update_yaxes(showgrid=False, automargin=True, ticklabelstandoff=8)
    return fig


def _gauge(score: float, p: Dict[str, str]) -> go.Figure:
    col = p["up"] if score >= 60 else p["ref"] if score >= 40 else p["down"]
    fig = go.Figure(go.Indicator(
        mode="gauge+number", value=score, number=dict(font=dict(size=40, color=p["text"]), valueformat=".0f"),
        gauge=dict(axis=dict(range=[0, 100], tickwidth=0, tickfont=dict(size=10, color=p["muted"])),
                   bar=dict(color=col, thickness=0.28), bgcolor="rgba(0,0,0,0)", borderwidth=0,
                   steps=[dict(range=[0, 35], color="rgba(239,68,68,0.16)"),
                          dict(range=[35, 50], color="rgba(245,158,11,0.14)"),
                          dict(range=[50, 65], color="rgba(132,204,22,0.14)"),
                          dict(range=[65, 100], color="rgba(34,197,94,0.18)")])))
    fig.update_layout(height=190, margin=dict(l=30, r=30, t=14, b=0), paper_bgcolor="rgba(0,0,0,0)",
                      font=dict(color=p["text"]))
    return fig


# ─────────────────────────── Các khối giao diện ───────────────────────────────
def _header(p: Dict[str, str], status: Dict, session: str):
    def pill(name: str, ok: Optional[bool]):
        c = p["up"] if ok else (p["ref"] if ok is None else p["down"])
        return f'<span class="mo-pill"><i class="mo-dot" style="background:{c}"></i>{name}</span>'
    dn = status.get("dnse", {}).get("available")
    vs = status.get("vnstock", {}).get("available")
    vt = status.get("vietstock", {}).get("available")
    pills = pill("DNSE", dn) + pill("vnstock", vs) + pill("Vietstock", vt if vt else None)
    if session:
        pills += f'<span class="mo-pill">📅 Phiên {session}</span>'
    pills += f'<span class="mo-pill">⏱ {datetime.now().strftime("%H:%M:%S")}</span>'
    _md(f'<div class="mo-head"><div><div class="mo-title">🏛️ Tổng Quan Thị Trường</div>'
        f'<div class="mo-sub">Toàn cảnh chứng khoán Việt Nam: chỉ số, độ rộng, dòng tiền theo ngành và cổ phiếu nổi bật'
        f'</div></div><div class="mo-pills">{pills}</div></div>')


def _index_cards(cards: Dict[str, Dict], p: Dict[str, str]):
    cols = st.columns(4)
    for col, code in zip(cols, INDEX_ORDER):
        c = cards.get(code, {})
        with col:
            if not c.get("available"):
                _md(f'<div class="mo-card"><div class="mo-lbl">{ms.INDEX_SYMBOLS.get(code, code)}</div>'
                    f'<div class="mo-val" style="color:{p["muted"]}">—</div>'
                    f'<div class="mo-meta"><span>Không lấy được dữ liệu</span></div></div>')
                continue
            clr = _color(c["change"], p)
            r = c["returns"]
            _md(f'<div class="mo-card"><div style="display:flex;justify-content:space-between;align-items:center">'
                f'<div class="mo-lbl">{c["name"]}</div><div class="mo-lbl" style="letter-spacing:0">{c["date"]}</div></div>'
                f'<div class="mo-val">{c["close"]:,.2f}</div>'
                f'<div class="mo-chg" style="color:{clr}">{_arrow(c["change"])} {c["change"]:+,.2f} '
                f'({c["change_pct"]:+.2f}%)</div>'
                f'<div style="margin-top:6px">{_spark(c["spark"], clr)}</div>'
                f'<div class="mo-meta"><span>Thấp–Cao: {c["low"]:,.1f} – {c["high"]:,.1f}</span></div>'
                f'<div class="mo-meta"><span>KL: {c["volume"] / 1e6:,.1f} tr</span>'
                f'<span>1Th <b style="color:{_color(r["1Th"], p)}">{_f(r["1Th"], 1, "%", True)}</b> · '
                f'YTD <b style="color:{_color(r["YTD"], p)}">{_f(r["YTD"], 1, "%", True)}</b></span></div></div>')


def _target_strip(p: Dict[str, str]):
    sym = st.session_state.get("current_symbol", "FPT")
    try:
        from data.ticker_directory import get_ticker_label
        label = get_ticker_label(sym)
    except Exception:
        label = sym
    df = _stock(sym, 90)
    info = f'<span style="color:{p["muted"]}">Chưa có dữ liệu giá</span>'
    spark = ""
    if df is not None and len(df) >= 2:
        last, prev = float(df["close"].iloc[-1]), float(df["close"].iloc[-2])
        chg = last - prev
        pct = chg / prev * 100 if prev else 0
        clr = _color(chg, p)
        vol = float(df["volume"].iloc[-1]) if "volume" in df.columns else 0
        info = (f'<b style="font-size:20px;color:{p["text"]}">{last:,.0f}</b> '
                f'<span style="color:{clr};font-weight:700">{_arrow(chg)} {chg:+,.0f} ({pct:+.2f}%)</span>'
                f'<span style="color:{p["muted"]};margin-left:14px">KL {vol:,.0f} CP · '
                f'GTGD {last * vol / 1e9:,.1f} tỷ</span>')
        spark = _spark(df["close"].tail(60).tolist(), clr, w=220, h=40)
    c1, c2 = st.columns([4, 1], vertical_alignment="center")
    with c1:
        _md(f'<div class="mo-card" style="display:flex;align-items:center;gap:18px;padding:10px 16px">'
            f'<div style="flex:1;min-width:0"><div class="mo-lbl">🎯 Cổ phiếu đang theo dõi</div>'
            f'<div style="font-weight:800;color:{p["accent"]};font-size:15px;white-space:nowrap;overflow:hidden;'
            f'text-overflow:ellipsis">{html.escape(label)}</div><div style="margin-top:2px">{info}</div></div>'
            f'<div style="width:220px;flex-shrink:0">{spark}</div></div>')
    with c2:
        if st.button(f"🔍 Phân tích {sym}", type="primary", use_container_width=True, key="mo_jump"):
            st.session_state["nav_page"] = "🔍 Phân Tích Cổ Phiếu"
            st.rerun()


def _health_panel(health: Dict, p: Dict[str, str]):
    _md('<div class="mo-lbl" style="margin-bottom:2px">Sức khỏe thị trường</div>')
    if not health.get("available"):
        st.info("Chưa đủ dữ liệu để chấm điểm.")
        return
    st.plotly_chart(_gauge(health["score"], p), use_container_width=True, theme=None, config={"displayModeBar": False})
    s = health["score"]
    clr = p["up"] if s >= 60 else p["ref"] if s >= 40 else p["down"]
    rows = "".join(
        f'<div class="mo-comp"><span>{v["label"]} <small>({v["weight"]}%)</small></span><b>{v["detail"]}</b></div>'
        f'<div class="mo-track"><i style="width:{max(2, v["score"]):.0f}%;background:{_color(v["score"] - 50, p)}"></i></div>'
        for v in health["components"].values() if v.get("score") is not None and not pd.isna(v["score"]))
    _md(f'<div style="text-align:center;font-weight:800;color:{clr};margin:-8px 0 8px">{health["label"]}</div>{rows}')
    st.caption("Điểm theo quy tắc (xu hướng, RSI, độ rộng, hiệu suất 20 phiên) – chỉ để tham khảo, không phải khuyến nghị.")


def _breadth_block(b: Dict, p: Dict[str, str]):
    if not b.get("available") or not b.get("total"):
        st.warning("Không lấy được dữ liệu cổ phiếu để tính độ rộng thị trường.")
        return
    t = b["total"]
    w = lambda n: n / t * 100 if t else 0  # noqa: E731
    _md(f'<div class="mo-card"><div style="display:flex;justify-content:space-between;align-items:center">'
        f'<div class="mo-lbl">Tương quan tăng / giảm · {t} mã · phiên {b["session"]}</div>'
        f'<div class="mo-lbl" style="letter-spacing:0">A/D = {_f(b["ad_ratio"], 2) if b["ad_ratio"] else "∞"}</div></div>'
        f'<div class="mo-bar"><div style="width:{w(b["advancing"]):.2f}%;background:{p["up"]}"></div>'
        f'<div style="width:{w(b["unchanged"]):.2f}%;background:{p["ref"]}"></div>'
        f'<div style="width:{w(b["declining"]):.2f}%;background:{p["down"]}"></div></div>'
        f'<div class="mo-legend"><span style="color:{p["up"]}">▲ {b["advancing"]} tăng ({w(b["advancing"]):.0f}%)</span>'
        f'<span style="color:{p["ref"]}">■ {b["unchanged"]} đứng giá</span>'
        f'<span style="color:{p["down"]}">▼ {b["declining"]} giảm ({w(b["declining"]):.0f}%)</span></div></div>')
    k = st.columns(5)
    kpis = [
        ("Biến động bình quân", _f(b["avg_change"], 2, "%", True), _color(b["avg_change"], p)),
        ("% mã trên MA20", _f(b["pct_above_ma20"], 0, "%"), _color((b["pct_above_ma20"] or 50) - 50, p)),
        ("Vượt đỉnh 20 phiên", f'{b["new_highs"]}', p["up"]),
        ("Thủng đáy 20 phiên", f'{b["new_lows"]}', p["down"]),
        ("Tổng GTGD rổ", _f(b["value_bn"], 0, " tỷ"), p["text"]),
    ]
    for col, (lbl, val, c) in zip(k, kpis):
        with col:
            _md(f'<div class="mo-kpi" style="margin-top:10px"><small>{lbl}</small><b style="color:{c}">{val}</b></div>')


def _movers_table(df: pd.DataFrame, p: Dict[str, str], extra: str) -> str:
    if df.empty:
        return f'<div style="color:{p["muted"]};padding:12px">Không có dữ liệu</div>'
    extra_head = {"value": "GTGD (tỷ)", "vol": "KL / TB20", "chg": "GTGD (tỷ)"}[extra]
    rows = []
    for i, r in enumerate(df.itertuples(), 1):
        clr = _color(r.change_pct, p)
        sector = r.sector.split(" ", 1)[1] if " " in r.sector and not r.sector[0].isalnum() else r.sector
        ex = (f"{r.vol_ratio:,.2f}×" if extra == "vol" and r.vol_ratio else _f(r.value_bn, 1))
        rows.append(
            f'<tr><td style="color:{p["muted"]};width:28px">{i}</td>'
            f'<td><span class="mo-sym">{r.symbol}</span> <small style="color:{p["muted"]}">{html.escape(sector)}</small></td>'
            f'<td>{r.close:,.0f}</td><td style="color:{clr}">{r.change:+,.0f}</td>'
            f'<td><span class="mo-badge" style="background:{clr}">{r.change_pct:+.2f}%</span></td>'
            f'<td>{r.volume:,.0f}</td><td>{ex}</td>'
            f'<td style="color:{_color(r.ret_20d, p)}">{_f(r.ret_20d, 1, "%", True)}</td>'
            f'<td style="width:120px">{_spark(r.spark, clr, w=110, h=26, fill=False)}</td></tr>')
    return (f'<div class="mo-card" style="padding:6px 8px;overflow-x:auto"><table class="mo-t"><thead><tr>'
            f'<th>#</th><th>Mã</th><th>Giá</th><th>+/-</th><th>%</th><th>Khối lượng</th><th>{extra_head}</th>'
            f'<th>20 phiên</th><th>30 phiên gần nhất</th></tr></thead><tbody>{"".join(rows)}</tbody></table></div>')


def _returns_table(rows: Dict[str, Dict], p: Dict[str, str]) -> str:
    keys = ["1T", "1Th", "3Th", "6Th", "YTD", "1N"]
    titles = ["1 tuần", "1 tháng", "3 tháng", "6 tháng", "Từ đầu năm", "1 năm"]
    head = "".join(f'<th title="{t}">{k}</th>' for k, t in zip(["1T", "1Th", "3Th", "6Th", "YTD", "1N"], titles))
    body = ""
    for name, r in rows.items():
        cells = "".join(f'<td style="color:{_color(r.get(k), p)};font-weight:700">{_f(r.get(k), 2, "%", True)}</td>'
                        for k in keys)
        body += f'<tr><td style="white-space:nowrap"><span class="mo-sym">{html.escape(name)}</span></td>{cells}</tr>'
    return (f'<div class="mo-card" style="padding:6px 8px;overflow-x:auto"><table class="mo-t mo-r"><thead><tr><th>Chỉ số / Mã</th>'
            f'{head}</tr></thead><tbody>{body}</tbody></table>'
            f'<div style="font-size:11px;color:{p["muted"]};padding:6px 10px">T = tuần · Th = tháng · N = năm · '
            f'YTD = từ đầu năm</div></div>')


def _open_pick():
    sym = st.session_state.get("mo_pick", "—")
    if sym and sym != "—":
        for k in ("current_symbol", "stock_symbol_input", "ta_symbol", "score_symbol", "bt_symbol", "pdf_symbol"):
            st.session_state[k] = sym
        st.session_state.pop("stock_analysis", None)
        st.session_state.pop("last_analyzed", None)
        st.session_state["nav_page"] = "🔍 Phân Tích Cổ Phiếu"
        st.session_state["mo_pick"] = "—"


# ─────────────────────────── Trang ────────────────────────────────────────────
def render():
    p = _pal()
    _md(_css(p))

    with st.spinner("Đang tải dữ liệu chỉ số..."):
        hist = {code: _idx(code, 1100 if code == "VNINDEX" else 400) for code in INDEX_ORDER}
    cards = {code: ms.index_card(code, df) for code, df in hist.items()}
    session = next((c["date"] for c in cards.values() if c.get("available")), "")

    h1, h2 = st.columns([6, 1], vertical_alignment="bottom")
    with h1:
        _header(p, _status(), session)
    with h2:
        if st.button("🔄 Làm mới", use_container_width=True, key="mo_refresh",
                     help="Xóa bộ nhớ tạm của trang và tải lại dữ liệu mới nhất"):
            _clear_cache()
            st.rerun()

    _index_cards(cards, p)
    st.markdown("<div style='height:12px'></div>", unsafe_allow_html=True)
    _target_strip(p)

    # ── Độ rộng (tính trước để dùng cho điểm sức khỏe) ──
    universes = ms.universe_options()
    uni_name = st.session_state.get("mo_universe", next(iter(universes)))
    if uni_name not in universes:
        uni_name = next(iter(universes))
    with st.spinner(f"Đang tải dữ liệu {len(universes[uni_name])} cổ phiếu..."):
        snap = _snapshot(tuple(universes[uni_name]))
    breadth = ms.breadth_stats(snap)

    # ── Biểu đồ chỉ số + sức khỏe ──
    _section("Diễn biến chỉ số", "Nến ngày · MA20 · MA50 · khối lượng")
    c_chart, c_health = st.columns([3, 1], gap="medium")
    with c_chart:
        o1, o2, o3 = st.columns([2.2, 2.6, 1.3])
        with o1:
            code = st.segmented_control("Chỉ số", INDEX_ORDER, default="VNINDEX", key="mo_idx",
                                        format_func=lambda c: SHORT_IDX.get(c, c),
                                        label_visibility="collapsed") or "VNINDEX"
        with o2:
            per = st.segmented_control("Kỳ", list(PERIODS), default="6Th", key="mo_period", help="Th = tháng, N = năm",
                                       label_visibility="collapsed") or "6Th"
        with o3:
            kind = st.segmented_control("Kiểu", ["Nến", "Đường"], default="Nến", key="mo_kind",
                                        label_visibility="collapsed") or "Nến"
        df = hist.get(code, pd.DataFrame())
        if df is not None and not df.empty:
            cutoff = pd.to_datetime(df["timestamp"]).max() - pd.Timedelta(days=PERIODS[per])
            view = df[pd.to_datetime(df["timestamp"]) >= cutoff - pd.Timedelta(days=80)]  # dư cho MA50
            fig = _index_chart(view, ms.INDEX_SYMBOLS.get(code, code), kind, p)
            fig.update_xaxes(range=[cutoff, pd.to_datetime(df["timestamp"]).max() + pd.Timedelta(days=2)])
            st.plotly_chart(fig, use_container_width=True, theme=None, config={"displayModeBar": False})
            if len(df) and pd.to_datetime(df["timestamp"]).min() > cutoff + pd.Timedelta(days=5):
                st.caption("Nguồn dữ liệu chỉ có lịch sử ngắn hơn kỳ đã chọn.")
        else:
            st.warning(f"Không tải được dữ liệu {ms.INDEX_SYMBOLS.get(code, code)}.")
    with c_health:
        _health_panel(ms.market_health(hist.get("VNINDEX"), breadth), p)

    # ── Độ rộng thị trường ──
    _section("Độ rộng thị trường", "Đo trên rổ cổ phiếu đã chọn – phiên gần nhất")
    st.selectbox("Rổ cổ phiếu", list(universes), key="mo_universe",
                 format_func=lambda n: f"{n} · {len(universes[n])} mã", label_visibility="collapsed")
    _breadth_block(breadth, p)

    if snap is None or snap.empty:
        return
    live = snap[~snap["stale"]]

    # ── Heatmap + ngành ──
    _section("Bản đồ nhiệt & dòng tiền theo ngành", "Diện tích = giá trị giao dịch · màu = % thay đổi")
    c_map, c_sec = st.columns([3, 2], gap="medium")
    with c_map:
        st.plotly_chart(_treemap(live, p), use_container_width=True, theme=None, config={"displayModeBar": False})
    with c_sec:
        sec = ms.sector_performance(live)
        horizon = st.segmented_control("Kỳ ngành", ["1D", "5D", "20D"], default="1D", key="mo_sec_h",
                                       format_func=lambda h: {"1D": "1 phiên", "5D": "5 phiên", "20D": "20 phiên"}[h],
                                       label_visibility="collapsed") or "1D"
        if not sec.empty:
            st.plotly_chart(_sector_bars(sec, horizon, p), use_container_width=True, theme=None, config={"displayModeBar": False})

    # ── Top cổ phiếu ──
    _section("Cổ phiếu nổi bật", f"Trong rổ {uni_name.split(' ', 1)[-1]}")
    n = 10
    t1, t2, t3, t4 = st.tabs(["📈 Tăng mạnh nhất", "📉 Giảm mạnh nhất", "💰 Giá trị giao dịch lớn", "⚡ Đột biến khối lượng"])
    with t1:
        _md(_movers_table(live.nlargest(n, "change_pct"), p, "chg"))
    with t2:
        _md(_movers_table(live.nsmallest(n, "change_pct"), p, "chg"))
    with t3:
        _md(_movers_table(live.nlargest(n, "value_bn"), p, "value"))
    with t4:
        _md(_movers_table(live.dropna(subset=["vol_ratio"]).nlargest(n, "vol_ratio"), p, "vol"))
    st.selectbox("Mở phân tích chi tiết", ["—"] + sorted(live["symbol"].tolist()), key="mo_pick",
                 format_func=lambda s: "🔎 Chọn mã để mở phân tích chi tiết…" if s == "—" else s,
                 on_change=_open_pick, label_visibility="collapsed")

    # ── So sánh hiệu suất ──
    target = st.session_state.get("current_symbol", "FPT")
    _section("So sánh hiệu suất", f"Chuẩn hóa = 100 · chỉ số và {target}")
    series, ret_rows = {}, {}
    for code in INDEX_ORDER:
        d = hist.get(code)
        if d is not None and not d.empty:
            d1 = d[pd.to_datetime(d["timestamp"]) >= pd.to_datetime(d["timestamp"]).max() - pd.Timedelta(days=365)]
            if code in ("VNINDEX", "VN30"):
                series[ms.INDEX_SYMBOLS[code]] = d1.set_index("timestamp")["close"]
            ret_rows[ms.INDEX_SYMBOLS[code]] = cards[code]["returns"] if cards[code].get("available") else {}
    sd = _stock(target, 400)
    if sd is not None and not sd.empty:
        sd1 = sd[pd.to_datetime(sd["timestamp"]) >= pd.to_datetime(sd["timestamp"]).max() - pd.Timedelta(days=365)]
        series[target] = sd1.set_index("timestamp")["close"]
        ret_rows[target] = ms.period_returns(sd)
    c_l, c_r = st.columns([1, 1], gap="medium")
    with c_l:
        if series:
            fig = line_comparison_chart(series, title="", height=340)
            fig.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                              margin=dict(l=8, r=8, t=10, b=8))
            st.plotly_chart(fig, use_container_width=True, theme=None, config={"displayModeBar": False})
    with c_r:
        if ret_rows:
            _md(_returns_table(ret_rows, p))

    # ── Chân trang ──
    status = _status()
    strat = status.get("strategy", {})
    _md(f'<div class="mo-foot">Nguồn: giá {strat.get("dnse_recent_days", 365)} ngày gần nhất từ DNSE, lịch sử cũ hơn từ '
        f'vnstock/Vietstock (đã nối chuỗi). Dữ liệu cuối ngày, có thể trễ so với bảng giá trực tuyến. '
        f'Bộ nhớ tạm của trang: 5 phút.</div>')
    with st.expander("🔧 Chi tiết kỹ thuật nguồn dữ liệu"):
        st.json(status, expanded=False)
