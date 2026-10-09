"""
Giao diện web:  streamlit run app.py

Tính năng mới:
  [1] Biểu đồ tương tác Plotly – nến, EMA20/50/SMA200, Bollinger Bands, RSI, Volume, điểm BUY/SELL
  [4] Stock Screener thông minh – lọc theo ROE, P/E, RS, thanh khoản; xếp hạng trực tiếp
"""
import datetime as dt
import os

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st

from analyzer import load_data, analyze
from report import build_pdf, chart_price, chart_fin, chart_rel

st.set_page_config(
    page_title="Phân tích cơ hội đầu tư cổ phiếu",
    page_icon="📈",
    layout="wide",
)
st.title("📈 Hệ thống phân tích cơ hội đầu tư cổ phiếu")
st.caption("Nhập mã cổ phiếu → hệ thống lấy dữ liệu, chấm điểm 3 trụ cột và xuất báo cáo PDF tự động.")

# =====================================================================
# SIDEBAR
# =====================================================================
with st.sidebar:
    st.header("Thiết lập")
    mode = st.radio(
        "Chế độ",
        ["Phân tích từng mã", "Quét thị trường", "📊 Stock Screener"],
    )
    if mode == "Phân tích từng mã":
        tickers = st.text_input("Mã cổ phiếu (cách nhau dấu phẩy)", "FPT")
    elif mode == "Quét thị trường":
        group = st.selectbox(
            "Rổ cổ phiếu", ["VN30", "VN100", "HNX30", "VNMidCap", "HOSE", "HNX"]
        )
        top_n = st.slider("Xuất PDF chi tiết cho top", 0, 10, 3)
        st.caption(
            "Bản miễn phí vnstock giới hạn request/phút: VN30 mất vài phút, HOSE có thể tới 30–60 phút."
        )
    else:  # Stock Screener
        screener_group = st.selectbox(
            "Rổ sàng lọc", ["VN30", "VN100", "HNX30", "Tự chọn"]
        )
        if screener_group == "Tự chọn":
            screener_tickers = st.text_input(
                "Danh sách mã (phẩy)", "FPT,HPG,VCB,MWG,VNM"
            )
    demo = st.toggle("Dùng dữ liệu mô phỏng (khi API lỗi)", value=False)
    run = st.button("Chạy", type="primary", use_container_width=True)
    st.markdown("---")
    st.markdown(
        "**Trọng số:** Chất lượng 35% · Định giá 30% · Động lượng 25% · Tin tức 10%"
    )


# =====================================================================
# TÍNH NĂNG 1 – BIỂU ĐỒ TƯƠNG TÁC PLOTLY
# =====================================================================

def _ema(series: pd.Series, span: int) -> pd.Series:
    return series.ewm(span=span, adjust=False).mean()


def _sma(series: pd.Series, window: int) -> pd.Series:
    return series.rolling(window).mean()


def _bollinger(series: pd.Series, window: int = 20, std: float = 2.0):
    mid = _sma(series, window)
    sigma = series.rolling(window).std()
    return mid - std * sigma, mid, mid + std * sigma


def _rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0).rolling(period).mean()
    loss = (-delta.clip(upper=0)).rolling(period).mean()
    rs = gain / loss.replace(0, np.nan)
    return 100 - 100 / (1 + rs)


def plotly_chart(a: dict, ticker: str,
                 show_ema20=True, show_ema50=True, show_sma200=True,
                 show_bb=False, timeframe="1Y") -> go.Figure:
    """Vẽ biểu đồ nến tương tác với các chỉ báo kỹ thuật."""
    px = a["px"].copy()

    # Lọc khung thời gian
    cutoffs = {"3M": 63, "6M": 126, "1Y": 252, "2Y": 504, "All": len(px)}
    n = cutoffs.get(timeframe, 252)
    px = px.tail(n).reset_index(drop=True)

    close = px["close"]
    fig = make_subplots(
        rows=3, cols=1,
        shared_xaxes=True,
        row_heights=[0.6, 0.2, 0.2],
        vertical_spacing=0.03,
        subplot_titles=(f"{ticker} – Giá", "Volume", "RSI(14)"),
    )

    # --- Nến ---
    fig.add_trace(
        go.Candlestick(
            x=px["time"], open=px["open"], high=px["high"],
            low=px["low"], close=close,
            name="Giá", increasing_line_color="#26a65b", decreasing_line_color="#e74c3c",
        ),
        row=1, col=1,
    )

    # --- Đường MA ---
    if show_ema20:
        fig.add_trace(go.Scatter(x=px["time"], y=_ema(close, 20), name="EMA20",
                                 line=dict(color="#f39c12", width=1.2)), row=1, col=1)
    if show_ema50:
        fig.add_trace(go.Scatter(x=px["time"], y=_ema(close, 50), name="EMA50",
                                 line=dict(color="#2980b9", width=1.2)), row=1, col=1)
    if show_sma200:
        fig.add_trace(go.Scatter(x=px["time"], y=_sma(close, 200), name="SMA200",
                                 line=dict(color="#8e44ad", width=1.2, dash="dot")), row=1, col=1)

    # --- Bollinger Bands ---
    if show_bb:
        bl, bm, bu = _bollinger(close)
        fig.add_trace(go.Scatter(x=px["time"], y=bu, name="BB Upper",
                                 line=dict(color="rgba(100,100,200,0.5)", width=1), showlegend=False), row=1, col=1)
        fig.add_trace(go.Scatter(x=px["time"], y=bm, name="BB Mid",
                                 line=dict(color="rgba(100,100,200,0.4)", width=1, dash="dash"),
                                 showlegend=False), row=1, col=1)
        fig.add_trace(go.Scatter(x=px["time"], y=bl, name="BB Lower",
                                 line=dict(color="rgba(100,100,200,0.5)", width=1),
                                 fill="tonexty", fillcolor="rgba(100,100,200,0.07)", showlegend=False), row=1, col=1)

    # --- Điểm BUY / SELL dựa trên Golden Cross / Death Cross ---
    ema20 = _ema(close, 20)
    ema50 = _ema(close, 50)
    cross_up = (ema20 > ema50) & (ema20.shift(1) <= ema50.shift(1))
    cross_dn = (ema20 < ema50) & (ema20.shift(1) >= ema50.shift(1))
    if cross_up.any():
        fig.add_trace(go.Scatter(
            x=px["time"][cross_up], y=close[cross_up] * 0.985,
            mode="markers", marker=dict(symbol="triangle-up", color="#26a65b", size=10),
            name="Golden Cross (BUY)"), row=1, col=1)
    if cross_dn.any():
        fig.add_trace(go.Scatter(
            x=px["time"][cross_dn], y=close[cross_dn] * 1.015,
            mode="markers", marker=dict(symbol="triangle-down", color="#e74c3c", size=10),
            name="Death Cross (SELL)"), row=1, col=1)

    # --- Giá mục tiêu & cắt lỗ ---
    if a.get("target"):
        fig.add_hline(y=a["target"], line_dash="dash", line_color="#26a65b",
                      annotation_text=f"Mục tiêu {a['target']:,.0f}", row=1, col=1)
    if a.get("stop"):
        fig.add_hline(y=a["stop"], line_dash="dot", line_color="#e74c3c",
                      annotation_text=f"Cắt lỗ {a['stop']:,.0f}", row=1, col=1)

    # --- Volume ---
    colors_vol = ["#26a65b" if c >= o else "#e74c3c"
                  for c, o in zip(px["close"], px["open"])]
    fig.add_trace(go.Bar(x=px["time"], y=px["volume"], name="Volume",
                         marker_color=colors_vol, showlegend=False), row=2, col=1)

    # --- RSI ---
    rsi_val = _rsi(close)
    fig.add_trace(go.Scatter(x=px["time"], y=rsi_val, name="RSI(14)",
                             line=dict(color="#e67e22", width=1.2)), row=3, col=1)
    fig.add_hline(y=70, line_dash="dash", line_color="red", line_width=0.8, row=3, col=1)
    fig.add_hline(y=30, line_dash="dash", line_color="green", line_width=0.8, row=3, col=1)
    fig.add_hrect(y0=40, y1=70, fillcolor="rgba(39,174,96,0.07)", line_width=0, row=3, col=1)

    fig.update_layout(
        height=700, xaxis_rangeslider_visible=False,
        template="plotly_dark", legend=dict(orientation="h", y=1.02),
        margin=dict(l=10, r=10, t=40, b=10),
    )
    fig.update_yaxes(title_text="Giá (đ)", row=1, col=1)
    fig.update_yaxes(title_text="KL", row=2, col=1)
    fig.update_yaxes(title_text="RSI", range=[0, 100], row=3, col=1)
    return fig


# =====================================================================
# TÍNH NĂNG 4 – STOCK SCREENER THÔNG MINH
# =====================================================================

VN30_LIST = [
    "ACB","BCM","BID","BVH","CTG","FPT","GAS","GVR","HDB","HPG",
    "LPB","MBB","MSN","MWG","PLX","SAB","SHB","SSB","SSI","STB",
    "TCB","TPB","VCB","VHM","VIB","VIC","VJC","VNM","VPB","VRE",
]
VN100_EXTRA = [
    "AGR","ANV","BCG","BMP","BSI","DBC","DCM","DHC","DIG","DPM",
    "DRC","EVF","FRT","GEX","GMD","HAH","HCM","HDC","HDG","IJC",
    "KBC","KDC","KDH","KSB","MSB","NAB","NLG","NVL","OCB","PDR",
    "PHR","PNJ","POW","PPC","PVD","PVT","REE","SBT","SCR","SCS",
    "SHS","SJS","SZC","TCH","TDM","TIP","TLG","TNH","VCI","VGC",
]
HNX30_LIST = [
    "CEO","CLH","DTD","HUT","L14","MBS","NRC","PLC","PVB","PVG",
    "SHN","SHS","TNG","VC3","VCS","VGS","VIF","VNR","VNS","VTS",
]
GROUPS = {"VN30": VN30_LIST, "VN100": VN30_LIST + VN100_EXTRA, "HNX30": HNX30_LIST}


def run_screener(tickers_list: list[str], demo: bool, progress_cb=None) -> pd.DataFrame:
    """Chạy phân tích nhanh từng mã và trả về DataFrame xếp hạng."""
    rows = []
    for i, t in enumerate(tickers_list, 1):
        try:
            data = load_data(t, demo=demo)
            a = analyze(data)
            last = a["fin"].iloc[-1]
            rows.append(dict(
                ticker=t,
                rec=a["rec"],
                total=round(a["total"], 1),
                quality=round(a["scores"]["quality"], 1),
                valuation=round(a["scores"]["valuation"], 1),
                momentum=round(a["scores"]["momentum"], 1),
                news_score=round(a["scores"].get("news", 0), 1),
                price=a["price"],
                target=a["target"],
                upside=round(a["upside"], 1) if a["upside"] is not None else None,
                pe=round(a["pe_now"], 1) if a["pe_now"] else None,
                pb=round(a["pb_now"], 1) if a["pb_now"] else None,
                roe=round(float(last.get("roe", np.nan)), 1),
                net_margin=round(float(last.get("net_margin", np.nan)), 1),
                rev_g=round(a["rev_g"], 1) if a["rev_g"] is not None else None,
                np_g=round(a["np_g"], 1) if a["np_g"] is not None else None,
                rs6=round(a["rs6"], 1) if a["rs6"] is not None else None,
                rsi=round(float(a["rsi"]), 1) if not pd.isna(a["rsi"]) else None,
                stop=a["stop"],
            ))
        except Exception as e:
            rows.append(dict(ticker=t, rec="LỖI", total=0, quality=0, valuation=0,
                             momentum=0, news_score=0, price=None, target=None, upside=None,
                             pe=None, pb=None, roe=None, net_margin=None, rev_g=None,
                             np_g=None, rs6=None, rsi=None, stop=None))
            st.toast(f"⚠️ {t}: {str(e)[:60]}", icon="⚠️")
        if progress_cb:
            progress_cb(i / len(tickers_list), f"Đã xử lý {i}/{len(tickers_list)}: {t}")
    return pd.DataFrame(rows)


def show_screener_ui(df: pd.DataFrame):
    """Hiển thị bộ lọc tương tác và bảng kết quả Stock Screener."""
    st.subheader("📊 Stock Screener – Sàng lọc cổ phiếu thông minh")
    valid = df[df["rec"] != "LỖI"].copy()

    # --- BỘ LỌC ---
    st.markdown("#### ⚙️ Bộ lọc tiêu chí")
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        min_roe = st.slider("ROE tối thiểu (%)", 0, 40, 10, 1)
        min_total = st.slider("Điểm tổng tối thiểu", 0, 100, 40, 5)
    with col2:
        max_pe = st.slider("P/E tối đa (0 = bỏ qua)", 0, 60, 0, 1)
        min_rs6 = st.slider("RS 6 tháng tối thiểu (điểm %)", -30, 30, 0, 1)
    with col3:
        recs = st.multiselect(
            "Khuyến nghị",
            ["MUA", "THEO DÕI / NẮM GIỮ", "TRÁNH / BÁN"],
            default=["MUA", "THEO DÕI / NẮM GIỮ"],
        )
        min_momentum = st.slider("Điểm động lượng tối thiểu", 0, 100, 0, 5)
    with col4:
        min_rsi = st.slider("RSI tối thiểu", 0, 100, 0, 5)
        max_rsi = st.slider("RSI tối đa", 0, 100, 100, 5)

    # Áp dụng bộ lọc
    mask = (
        (valid["total"] >= min_total)
        & (valid["roe"].fillna(0) >= min_roe)
        & (valid["rs6"].fillna(-999) >= min_rs6)
        & (valid["momentum"] >= min_momentum)
        & (valid["rsi"].fillna(50).between(min_rsi, max_rsi))
    )
    if recs:
        mask &= valid["rec"].isin(recs)
    if max_pe > 0:
        mask &= valid["pe"].fillna(999) <= max_pe

    filtered = valid[mask].sort_values("total", ascending=False).reset_index(drop=True)
    filtered.index += 1

    # --- TỔNG QUAN ---
    st.markdown("#### 📋 Tổng quan")
    ov1, ov2, ov3, ov4, ov5 = st.columns(5)
    counts = filtered["rec"].value_counts()
    ov1.metric("Tổng mã lọc được", len(filtered))
    ov2.metric("🟢 MUA", counts.get("MUA", 0))
    ov3.metric("🟡 THEO DÕI", counts.get("THEO DÕI / NẮM GIỮ", 0))
    ov4.metric("🔴 TRÁNH / BÁN", counts.get("TRÁNH / BÁN", 0))
    ov5.metric("Điểm TB", f"{filtered['total'].mean():.1f}" if len(filtered) else "—")

    # --- BIỂU ĐỒ BỌT (Chất lượng × Định giá, kích thước = động lượng) ---
    if len(filtered) >= 2:
        st.markdown("#### 🗺️ Bản đồ cơ hội (Chất lượng × Định giá)")
        color_map = {"MUA": "#26a65b", "THEO DÕI / NẮM GIỮ": "#f39c12", "TRÁNH / BÁN": "#e74c3c"}
        bubble = go.Figure()
        for rec_type, grp in filtered.groupby("rec"):
            bubble.add_trace(go.Scatter(
                x=grp["valuation"], y=grp["quality"],
                mode="markers+text", text=grp["ticker"], textposition="top center",
                marker=dict(
                    size=grp["momentum"].fillna(50) / 3 + 8,
                    color=color_map.get(rec_type, "#aaa"), opacity=0.8,
                    line=dict(color="white", width=0.5),
                ),
                name=rec_type,
                hovertemplate=(
                    "<b>%{text}</b><br>Định giá: %{x}<br>Chất lượng: %{y}"
                    "<br>Điểm tổng: %{customdata[0]}<br>P/E: %{customdata[1]}<br>ROE: %{customdata[2]}%"
                    "<extra></extra>"
                ),
                customdata=grp[["total", "pe", "roe"]].values,
            ))
        bubble.add_shape(type="line", x0=50, x1=50, y0=0, y1=100,
                         line=dict(color="grey", dash="dot", width=1))
        bubble.add_shape(type="line", x0=0, x1=100, y0=50, y1=50,
                         line=dict(color="grey", dash="dot", width=1))
        bubble.add_annotation(x=92, y=92, text="Tốt & Rẻ", showarrow=False,
                               font=dict(color="#26a65b", size=11))
        bubble.update_layout(
            template="plotly_dark", height=420,
            xaxis_title="Điểm định giá (cao = rẻ)",
            yaxis_title="Điểm chất lượng",
            margin=dict(l=10, r=10, t=20, b=10),
            xaxis=dict(range=[-3, 103]), yaxis=dict(range=[-3, 103]),
        )
        st.plotly_chart(bubble, use_container_width=True)

    # --- BẢNG KẾT QUẢ ---
    st.markdown(f"#### 📄 Kết quả ({len(filtered)} mã)")
    if filtered.empty:
        st.info("Không có mã nào thỏa mãn bộ lọc. Hãy nới lỏng tiêu chí.")
        return

    def color_rec(val):
        c = {"MUA": "color: #26a65b; font-weight:bold",
             "THEO DÕI / NẮM GIỮ": "color: #f39c12; font-weight:bold",
             "TRÁNH / BÁN": "color: #e74c3c; font-weight:bold"}.get(val, "")
        return c

    display_cols = ["ticker", "rec", "total", "quality", "valuation", "momentum",
                    "price", "target", "upside", "pe", "pb", "roe", "rs6", "rsi"]
    col_labels = {
        "ticker": "Mã", "rec": "Khuyến nghị", "total": "Điểm", "quality": "Chất lượng",
        "valuation": "Định giá", "momentum": "Động lượng",
        "price": "Giá", "target": "Mục tiêu", "upside": "Dư địa %",
        "pe": "P/E", "pb": "P/B", "roe": "ROE %", "rs6": "RS 6T", "rsi": "RSI",
    }
    show_df = filtered[display_cols].rename(columns=col_labels)
    styled = show_df.style.applymap(color_rec, subset=["Khuyến nghị"])
    st.dataframe(styled, use_container_width=True, height=420)

    # --- XUẤT CSV ---
    csv = filtered.to_csv(index_label="hang", encoding="utf-8-sig").encode("utf-8-sig")
    st.download_button(
        "⬇️ Tải kết quả CSV",
        data=csv,
        file_name=f"screener_{dt.date.today():%Y%m%d}.csv",
        mime="text/csv",
    )


# =====================================================================
# HIỂN THỊ PHÂN TÍCH TỪNG MÃ (có thêm biểu đồ Plotly)
# =====================================================================

def show(ticker):
    with st.spinner(f"Đang lấy dữ liệu {ticker}..."):
        data = load_data(ticker, demo=demo)
        a = analyze(data)

    st.subheader(f"{data['ticker']} – {data['name']}")
    if demo:
        st.warning("Đang dùng DỮ LIỆU MÔ PHỎNG, không phản ánh thực tế.")

    c = st.columns(5)
    c[0].metric("Khuyến nghị", a["rec"], f"{a['total']:.0f}/100 điểm", delta_color="off")
    c[1].metric("Giá hiện tại", f"{a['price']:,.0f}")
    c[2].metric(
        "Giá mục tiêu", f"{a['target']:,.0f}" if a["target"] else "N/A",
        f"{a['upside']:+.1f}%" if a["upside"] is not None else None,
    )
    c[3].metric("Cắt lỗ gợi ý", f"{a['stop']:,.0f}" if a["stop"] else "N/A")
    c[4].metric("RSI(14)", f"{a['rsi']:.0f}")

    s = a["scores"]
    st.progress(s["quality"] / 100, text=f"Chất lượng DN: {s['quality']:.0f}/100")
    st.progress(s["valuation"] / 100, text=f"Định giá: {s['valuation']:.0f}/100")
    st.progress(s["momentum"] / 100, text=f"Động lượng: {s['momentum']:.0f}/100")

    for cm in a["comments"]:
        st.markdown(f"- {cm}")

    # ---- [TÍNH NĂNG 1] Biểu đồ tương tác Plotly ----
    st.markdown("#### 📊 Biểu đồ kỹ thuật tương tác")
    opt_col1, opt_col2, opt_col3, opt_col4, opt_col5, opt_col6 = st.columns(6)
    with opt_col1:
        tf = st.selectbox("Khung thời gian", ["3M", "6M", "1Y", "2Y", "All"],
                          index=2, key=f"tf_{ticker}")
    with opt_col2:
        show_ema20 = st.checkbox("EMA20", value=True, key=f"ema20_{ticker}")
    with opt_col3:
        show_ema50 = st.checkbox("EMA50", value=True, key=f"ema50_{ticker}")
    with opt_col4:
        show_sma200 = st.checkbox("SMA200", value=True, key=f"sma200_{ticker}")
    with opt_col5:
        show_bb = st.checkbox("Bollinger Bands", value=False, key=f"bb_{ticker}")
    with opt_col6:
        st.markdown("")  # placeholder

    fig = plotly_chart(a, ticker, show_ema20, show_ema50, show_sma200, show_bb, tf)
    st.plotly_chart(fig, use_container_width=True)

    # ---- Biểu đồ tài chính tĩnh (matplotlib) ----
    c1, c2 = st.columns(2)
    c1.image(chart_fin(a))
    c2.image(chart_rel(a))

    # ---- Tin tức ----
    nw = data.get("news") or {}
    st.markdown(f"**Tin tức gần đây** · nguồn: {nw.get('source')}")
    if nw.get("n"):
        show_news = nw["items"][["date", "title", "sentiment"]].copy()
        show_news["date"] = show_news["date"].dt.strftime("%d/%m/%Y")
        st.dataframe(show_news, use_container_width=True, hide_index=True)

    mk = data.get("market_news") or {}
    if mk.get("n"):
        with st.expander(
            f"Bối cảnh thị trường · tâm lý {mk['score']:+.2f} · {mk.get('source')}",
            expanded=False,
        ):
            st.write(" | ".join(f"{k}: {v:+.2f}" for k, v in mk.get("by_topic", {}).items()))
            st.dataframe(
                mk["items"][["topic", "title", "sentiment"]],
                use_container_width=True, hide_index=True,
            )

    pr = data.get("peers") or {}
    if pr:
        with st.expander(f"So sánh ngành: {pr['group']} ({pr['n']} DN)"):
            st.dataframe(pr["peers"].round(1), use_container_width=True, hide_index=True)
            st.caption(
                f"Trung vị ngành – ROE {pr['roe']:.1f}%, biên LN {pr['net_margin']:.1f}%, "
                f"tăng trưởng DT {pr['rev_g']:.1f}%"
            )

    with st.expander("Kiểm soát chất lượng dữ liệu"):
        chk = data.get("check")
        if chk is not None and len(chk):
            st.dataframe(chk.round(2), use_container_width=True, hide_index=True)
        else:
            st.write("Chưa đối chiếu chéo được với vnstock trong lần chạy này.")
        for n_ in data.get("notes", []):
            st.write("• " + n_)

    with st.expander("Bảng chỉ số tài chính & giải trình chấm điểm"):
        st.dataframe(a["fin"].set_index("year").round(2), use_container_width=True)
        for k, name in [("quality", "Chất lượng"), ("valuation", "Định giá"), ("momentum", "Động lượng")]:
            st.markdown(f"**{name}**")
            st.dataframe(pd.DataFrame(a["checks"][k]), use_container_width=True, hide_index=True)

    out = build_pdf(data, a, f"output/{data['ticker']}_{dt.date.today():%Y%m%d}.pdf")
    with open(out, "rb") as f:
        st.download_button(
            f"⬇️ Tải báo cáo PDF {data['ticker']}", f,
            file_name=os.path.basename(out), mime="application/pdf", type="primary",
        )
    st.caption(
        f"Nguồn: {data['source']} · phiên cuối {data['last_session']} · tạo lúc {data['fetched_at']}"
    )
    st.divider()


# =====================================================================
# QUÉT THỊ TRƯỜNG (giữ nguyên logic cũ)
# =====================================================================

def show_market():
    from screener import run_screen
    bar = st.progress(0.0, text="Bắt đầu quét...")
    df, mpdf, dpdfs, failed = run_screen(
        group, demo=demo, top=top_n,
        progress=lambda p, m: bar.progress(p, text=m),
    )
    bar.empty()
    counts = df["rec"].value_counts()
    c = st.columns(4)
    c[0].metric("MUA", counts.get("MUA", 0))
    c[1].metric("THEO DÕI / NẮM GIỮ", counts.get("THEO DÕI / NẮM GIỮ", 0))
    c[2].metric("TRÁNH / BÁN", counts.get("TRÁNH / BÁN", 0))
    c[3].metric("Điểm TB", f"{df['total'].mean():.0f}")
    from news import get_market_news, demo_market_news
    mk = demo_market_news() if demo else get_market_news()
    if mk.get("n"):
        st.markdown(
            f"**Tâm lý thị trường: {mk['score']:+.2f}** · "
            + " | ".join(f"{k}: {v:+.2f}" for k, v in mk.get("by_topic", {}).items())
        )
        st.dataframe(mk["items"][["topic", "title", "sentiment"]], use_container_width=True, hide_index=True)
    if failed:
        st.warning("Lỗi dữ liệu: " + ", ".join(t for t, _ in failed))
    st.dataframe(df.round(1), use_container_width=True)
    with open(mpdf, "rb") as f:
        st.download_button(
            "⬇️ Tải PDF sàng lọc thị trường", f,
            file_name=os.path.basename(mpdf), mime="application/pdf", type="primary",
        )
    for p in dpdfs:
        with open(p, "rb") as f:
            st.download_button(
                f"⬇️ PDF chi tiết {os.path.basename(p)}", f,
                file_name=os.path.basename(p), mime="application/pdf",
            )


# =====================================================================
# ĐIỀU PHỐI CHÍNH
# =====================================================================

if run:
    if mode == "📊 Stock Screener":
        if screener_group == "Tự chọn":
            ticker_list = [t.strip().upper() for t in screener_tickers.split(",") if t.strip()]
        else:
            ticker_list = GROUPS.get(screener_group, VN30_LIST)
        bar = st.progress(0.0, text="Đang chạy screener...")
        df_screen = run_screener(ticker_list, demo, progress_cb=lambda p, m: bar.progress(p, text=m))
        bar.empty()
        show_screener_ui(df_screen)

    elif mode == "Quét thị trường":
        try:
            show_market()
        except Exception as e:
            st.error(f"Quét thất bại: {e}")

    else:  # Phân tích từng mã
        for t in [x.strip().upper() for x in tickers.split(",") if x.strip()]:
            try:
                show(t)
            except Exception as e:
                st.error(
                    f"{t}: không lấy được dữ liệu ({e}). Thử lại hoặc bật chế độ dữ liệu mô phỏng."
                )
