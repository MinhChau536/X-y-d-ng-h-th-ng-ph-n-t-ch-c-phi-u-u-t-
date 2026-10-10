"""
PDF Report Generator – Định dạng Báo cáo Phân tích Công ty Chứng khoán Chuyên nghiệp.

Tích hợp toàn diện lý thuyết định lượng của hệ thống:
  - Thẻ điểm cơ hội đầu tư đa chiều (Opportunity Score 0–100)
  - Phân tích kỹ thuật (Giá, MA50, MA200, RSI, MACD, ATR, Hỗ trợ / Kháng cự)
  - Phân tích cơ bản (Doanh thu, LNST, ROE, ROA, Biên lợi nhuận, Đòn bẩy Nợ/VCSH)
  - Mô hình định giá (P/E, P/B, Giá trị hợp lý, Dư địa tăng giá, Chiết khấu dòng tiền DCF)
  - Quản trị rủi ro (Biến động Volatility, Max Drawdown, Cắt lỗ gợi ý 2×ATR)
  - Động lượng & Sức mạnh tương đối (Mansfield Relative Strength vs VN-Index)
  - Luận điểm đầu tư & Khuyến nghị tự động
"""
from __future__ import annotations

import io
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from fpdf import FPDF

from analytics.period_utils import key_to_label
from config.settings import settings

logger = logging.getLogger(__name__)

# ── Bảng màu chuẩn báo cáo tài chính tổ chức ──
NAVY = (14, 42, 82)        # #0e2a52: Xanh Navy sang trọng
GREY = (110, 110, 110)     # #6e6e6e: Xám trung tính
LIGHT = (242, 245, 250)    # #f2f5fa: Nền bảng xanh nhạt
WHITE = (255, 255, 255)
GREEN = (16, 128, 64)      # #108040: Xanh tích cực
RED = (190, 30, 45)        # #be1e2d: Đỏ cảnh báo / tiêu cực
AMBER = (210, 135, 10)     # #d2870a: Vàng cam trung tính
BORDER = (218, 224, 233)


def _font_paths() -> Tuple[Optional[str], Optional[str]]:
    """
    Ưu tiên DejaVuSans (đi kèm matplotlib) để hỗ trợ đầy đủ 100% tiếng Việt
    và các ký tự đặc biệt (✓, ✗, ▲, ▼, •).
    Dự phòng Arial từ Windows Fonts.
    """
    mpl = Path(matplotlib.get_data_path()) / "fonts" / "ttf"
    dv_reg = mpl / "DejaVuSans.ttf"
    dv_bold = mpl / "DejaVuSans-Bold.ttf"
    if dv_reg.exists() and dv_bold.exists():
        return str(dv_reg), str(dv_bold)

    win = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts"
    if (win / "arial.ttf").exists() and (win / "arialbd.ttf").exists():
        return str(win / "arial.ttf"), str(win / "arialbd.ttf")

    return None, None


def _n(x, d=0, suf="") -> str:
    """Format số an toàn."""
    if x is None or pd.isna(x):
        return "N/A"
    try:
        val = float(x)
        return f"{val:,.{d}f}{suf}"
    except (ValueError, TypeError):
        return str(x)


# ─────────────────────────────────────────────────────────────────────────────
# Vẽ biểu đồ phân tích (Matplotlib engine)
# ─────────────────────────────────────────────────────────────────────────────

def _fig_to_png(fig) -> io.BytesIO:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=160, bbox_inches="tight")
    plt.close(fig)
    buf.seek(0)
    return buf


def _generate_price_chart(px: pd.DataFrame, ticker: str, target_price: Optional[float], stop_loss: Optional[float]) -> io.BytesIO:
    """Biểu đồ giá 12 tháng + MA50 + MA200 + Giá mục tiêu + Cắt lỗ + RSI(14)."""
    if px is None or px.empty:
        fig, ax = plt.subplots(figsize=(9.2, 2.2))
        ax.text(0.5, 0.5, "Không có dữ liệu giá lịch sử – không vẽ biểu đồ kỹ thuật",
                ha="center", va="center", color="#6e6e6e", fontsize=9)
        ax.axis("off")
        return _fig_to_png(fig)
    fig, (ax1, ax2) = plt.subplots(
        2, 1, figsize=(9.2, 4.4), sharex=True,
        gridspec_kw={"height_ratios": [3.2, 1.0], "hspace": 0.08}
    )

    time_series = px["timestamp"] if "timestamp" in px.columns else px["time"] if "time" in px.columns else px.index
    times = pd.to_datetime(time_series)
    closes = px["close"].values

    ax1.plot(times, closes, color="#0e2a52", lw=1.4, label="Giá đóng cửa")

    # MA50
    ma50_col = "SMA_50" if "SMA_50" in px.columns else "ma50" if "ma50" in px.columns else None
    if ma50_col and px[ma50_col].notna().any():
        ax1.plot(times, px[ma50_col].values, color="#e08a00", lw=1.1, label="MA50")

    # MA200
    ma200_col = "SMA_200" if "SMA_200" in px.columns else "ma200" if "ma200" in px.columns else None
    if ma200_col and px[ma200_col].notna().any():
        ax1.plot(times, px[ma200_col].values, color="#2a9d8f", lw=1.1, label="MA200")

    # Target & Stop loss
    if target_price and target_price > 0:
        ax1.axhline(target_price, color="#108040", ls="--", lw=1.1, label=f"Giá mục tiêu ({target_price:,.0f})")
    if stop_loss and stop_loss > 0:
        ax1.axhline(stop_loss, color="#be1e2d", ls=":", lw=1.1, label=f"Cắt lỗ 2xATR ({stop_loss:,.0f})")

    ax1.set_title(f"{ticker} – Diễn biến giá 12 tháng & Hệ thống chỉ báo kỹ thuật", fontsize=10, fontweight="bold", color="#0e2a52", loc="left")
    ax1.legend(fontsize=7, loc="upper left", ncol=5, frameon=True, framealpha=0.85, facecolor="#ffffff", edgecolor="#e2e8f0")
    ax1.grid(color="#e2e8f0", linestyle="--", linewidth=0.6, alpha=0.8)
    ax1.yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda x, p: f"{x:,.0f}"))

    # RSI
    rsi_col = "RSI" if "RSI" in px.columns else "rsi" if "rsi" in px.columns else None
    if rsi_col and px[rsi_col].notna().any():
        ax2.plot(times, px[rsi_col].values, color="#4a5568", lw=1.0)
    else:
        ax2.text(0.5, 0.5, "Chưa đủ dữ liệu tính RSI", transform=ax2.transAxes,
                 ha="center", va="center", color="#6e6e6e", fontsize=7)

    ax2.axhspan(30, 70, color="#0e2a52", alpha=0.08)
    ax2.axhline(70, color="#be1e2d", ls="--", lw=0.6, alpha=0.6)
    ax2.axhline(30, color="#108040", ls="--", lw=0.6, alpha=0.6)
    ax2.set_ylabel("RSI (14)", fontsize=7.5, color="#4a5568")
    ax2.set_ylim(0, 100)
    ax2.grid(color="#e2e8f0", linestyle="--", linewidth=0.5, alpha=0.8)

    for ax in (ax1, ax2):
        for s in ("top", "right"):
            ax.spines[s].set_visible(False)
        ax.spines["left"].set_color("#cbd5e1")
        ax.spines["bottom"].set_color("#cbd5e1")
        ax.tick_params(colors="#4a5568", labelsize=7)

    return _fig_to_png(fig)


def _generate_fin_chart(fin_df: pd.DataFrame) -> io.BytesIO:
    """Biểu đồ Doanh thu & LNST theo kỳ báo cáo (số liệu thật từ BCTC)."""
    fig, ax = plt.subplots(figsize=(4.4, 2.6))
    if fin_df is not None and not fin_df.empty and fin_df["revenue"].notna().any():
        fin_df = fin_df.fillna({"revenue": 0, "npat": 0})
        years = fin_df["period"].astype(str).tolist()
        rev = (fin_df["revenue"] / 1e9 if fin_df["revenue"].max() > 1e7 else fin_df["revenue"]).tolist()
        npat = (fin_df["npat"] / 1e9 if fin_df["npat"].max() > 1e7 else fin_df["npat"]).tolist()
        x = np.arange(len(years))
        width = 0.36
        ax.bar(x - width/2, rev, width=width, color="#0e2a52", label="Doanh thu")
        ax.bar(x + width/2, npat, width=width, color="#e08a00", label="LNST")
        ax.set_xticks(x)
        ax.set_xticklabels(years, fontsize=7.5)
    else:
        ax.text(0.5, 0.5, "Không đủ dữ liệu BCTC", ha="center", va="center", color="#6e6e6e")
        ax.set_xticks([])
        ax.set_yticks([])

    ax.set_title("Doanh thu & LNST (tỷ đồng)", fontsize=8.5, fontweight="bold", color="#0e2a52", loc="left")
    if ax.get_legend_handles_labels()[0]:
        ax.legend(fontsize=7, frameon=False, loc="upper left")
    ax.grid(axis="y", color="#e2e8f0", linestyle="--", linewidth=0.6, alpha=0.8)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    ax.spines["left"].set_color("#cbd5e1")
    ax.spines["bottom"].set_color("#cbd5e1")
    ax.tick_params(colors="#4a5568", labelsize=7)
    return _fig_to_png(fig)


def _generate_rel_chart(px: pd.DataFrame, idx: Optional[pd.DataFrame]) -> io.BytesIO:
    """Sức mạnh tương đối 6 tháng so với VN-Index (gốc = 100)."""
    fig, ax = plt.subplots(figsize=(4.4, 2.6))
    tail_px = px.tail(126).copy() if px is not None else pd.DataFrame()
    if not tail_px.empty and len(tail_px) >= 5:
        p_base = tail_px["close"].iloc[0]
        p_norm = (tail_px["close"] / p_base) * 100
        time_p = pd.to_datetime(tail_px["timestamp"] if "timestamp" in tail_px.columns else tail_px["time"] if "time" in tail_px.columns else tail_px.index)
        ax.plot(time_p, p_norm, color="#0e2a52", lw=1.4, label="Cổ phiếu")

        if idx is not None and not idx.empty and "close" in idx.columns:
            tail_idx = idx.tail(126).copy()
            i_base = tail_idx["close"].iloc[0]
            i_norm = (tail_idx["close"] / i_base) * 100
            time_i = pd.to_datetime(tail_idx["timestamp"] if "timestamp" in tail_idx.columns else tail_idx["time"] if "time" in tail_idx.columns else tail_idx.index)
            ax.plot(time_i, i_norm, color="#94a3b8", lw=1.2, ls="--", label="VN-Index")

        ax.axhline(100, color="#cbd5e1", lw=0.7, ls=":")
        ax.set_title("Sức mạnh tương đối 6 tháng (gốc = 100)", fontsize=8.5, fontweight="bold", color="#0e2a52", loc="left")
        ax.legend(fontsize=7, frameon=False, loc="upper left")
        ax.grid(color="#e2e8f0", linestyle="--", linewidth=0.6, alpha=0.8)
        ax.tick_params(axis="x", labelsize=6.5, rotation=25)
    else:
        ax.text(0.5, 0.5, "Không đủ dữ liệu lịch sử", ha="center", va="center", color="#6e6e6e")
        ax.set_xticks([])
        ax.set_yticks([])

    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    ax.spines["left"].set_color("#cbd5e1")
    ax.spines["bottom"].set_color("#cbd5e1")
    ax.tick_params(colors="#4a5568", labelsize=7)
    return _fig_to_png(fig)


# ─────────────────────────────────────────────────────────────────────────────
# Lớp Báo Cáo FPDF A4 Chuẩn Tổ Chức
# ─────────────────────────────────────────────────────────────────────────────

class EquityReportPDF(FPDF):
    """FPDF canvas tùy biến chuẩn hóa báo cáo phân tích công ty chứng khoán."""

    def __init__(self, meta: Dict[str, Any]):
        super().__init__(orientation="P", unit="mm", format="A4")
        self.meta = meta
        reg_font, bold_font = _font_paths()
        if reg_font and bold_font:
            self.add_font("VN", "", reg_font)
            self.add_font("VN", "B", bold_font)
            self.has_vn = True
        else:
            self.has_vn = False

        self.set_auto_page_break(True, margin=14)
        self.set_margins(14, 14, 14)

    def header(self):
        # Băng Header xanh Navy trên đầu trang
        self.set_fill_color(*NAVY)
        self.rect(0, 0, 210, 8.5, "F")
        self.set_xy(14, 1.8)
        self.set_font("VN" if self.has_vn else "Helvetica", "B", 7.5)
        self.set_text_color(255, 255, 255)
        self.cell(0, 5, "HỆ THỐNG PHÂN TÍCH CƠ HỘI ĐẦU TƯ CỔ PHIẾU  |  BÁO CÁO ĐỊNH LƯỢNG TỰ ĐỘNG", align="L")
        self.set_xy(14, 12)
        self.set_text_color(0, 0, 0)

    def footer(self):
        self.set_y(-10)
        self.set_font("VN" if self.has_vn else "Helvetica", "", 6.8)
        self.set_text_color(*GREY)
        sess = self.meta.get("last_session", datetime.now().strftime("%d/%m/%Y"))
        gen_time = self.meta.get("fetched_at", datetime.now().strftime("%H:%M %d/%m/%Y"))
        src = self.meta.get("data_source", "Vnstock / DNSE / BCTC Niêm Yết")
        self.cell(140, 4, f"Dữ liệu: {src}  |  Phiên: {sess}  |  Khởi tạo: {gen_time}", align="L")
        self.cell(0, 4, f"Trang {self.page_no()}/{{nb}}", align="R")

    def h2(self, txt: str):
        """Tiêu đề mục có đường viền kẻ gạch dưới xanh navy trang nhã."""
        self.ln(2.5)
        self.set_font("VN" if self.has_vn else "Helvetica", "B", 10.5)
        self.set_text_color(*NAVY)
        self.cell(0, 6, txt, new_x="LMARGIN", new_y="NEXT")
        self.set_draw_color(*BORDER)
        self.set_line_width(0.4)
        self.line(self.l_margin, self.get_y(), 196, self.get_y())
        self.ln(2.2)
        self.set_text_color(0, 0, 0)


# ─────────────────────────────────────────────────────────────────────────────
# Bộ Điều Phối & Xử Lý Dữ Liệu Báo Cáo
# ─────────────────────────────────────────────────────────────────────────────

class PDFReportGenerator:
    """Tạo báo cáo phân tích đầu tư PDF định dạng tổ chức tài chính chuyên nghiệp."""

    def __init__(self):
        settings.REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    SECTIONS = {
        "summary": "Tổng quan & khuyến nghị",
        "technical": "Phân tích kỹ thuật & biểu đồ",
        "financials": "Báo cáo tài chính nhiều năm",
        "ratios": "Chỉ số tài chính (tính từ BCTC)",
        "peers": "So sánh với ngành",
        "scoring": "Giải trình chấm điểm & phương pháp",
    }
    DEFAULT_SECTIONS = ["summary", "technical", "financials", "ratios", "peers", "scoring"]

    def generate(
        self,
        analysis: Dict[str, Any],
        report_type: str = "full",
        output_path: Optional[str] = None,
        sections: Optional[List[str]] = None,
    ) -> bytes:
        """
        Tạo báo cáo PDF theo các mục người dùng chọn và trả về bytes.
        report_type "short" = Tổng quan + Kỹ thuật + Chấm điểm; "full" = tất cả các mục.
        """
        if sections is None:
            sections = ["summary", "technical", "scoring"] if report_type == "short" else list(self.DEFAULT_SECTIONS)
        sections = [s for s in self.DEFAULT_SECTIONS if s in sections] or ["summary"]
        data, a = self._prepare_data(analysis)

        pdf = EquityReportPDF(data)
        pdf.alias_nb_pages()
        renderers = {
            "summary": self._render_page_1,
            "technical": self._render_technical,
            "financials": self._render_financials,
            "ratios": self._render_ratios,
            "peers": self._render_peers,
            "scoring": self._render_page_3,
        }
        for sec in sections:
            # mục ngắn được xếp nối tiếp, mục dài sang trang mới
            if sec in ("summary", "technical", "financials", "scoring") or pdf.page == 0 or pdf.get_y() > 200:
                pdf.add_page()
            renderers[sec](pdf, data, a)

        pdf_bytes = bytes(pdf.output())
        symbol = data["ticker"]
        if output_path is None:
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_path = str(settings.REPORTS_DIR / f"{symbol}_{report_type}_{ts}.pdf")
        with open(output_path, "wb") as f:
            f.write(pdf_bytes)
        logger.info("PDF generated successfully: %s (%d bytes)", output_path, len(pdf_bytes))
        return pdf_bytes

    # ─────────────────────────────────────────────────────────────────────────
    # Dàn trang chi tiết
    # ─────────────────────────────────────────────────────────────────────────

    def _render_page_1(self, pdf: EquityReportPDF, data: dict, a: dict):
        ticker = data["ticker"]
        name = data["name"]
        industry = data["industry"]

        # Ticker & Công ty
        pdf.set_font("VN" if pdf.has_vn else "Helvetica", "B", 20)
        pdf.set_text_color(*NAVY)
        pdf.cell(0, 9, ticker, new_x="LMARGIN", new_y="NEXT")

        pdf.set_font("VN" if pdf.has_vn else "Helvetica", "", 9.2)
        pdf.set_text_color(*GREY)
        sub_title = f"{name}" + (f"  •  {industry}" if industry else "")
        pdf.cell(0, 5, sub_title, new_x="LMARGIN", new_y="NEXT")
        pdf.ln(2.5)

        # Hộp Khuyến Nghị & 4 Chỉ số then chốt (Bố cục ngang đẳng cấp)
        y0 = pdf.get_y()
        rec_color = a["rec_color"]

        # Hộp Khuyến nghị bên trái (rộng 58mm, cao 27mm)
        pdf.set_fill_color(*rec_color)
        pdf.rect(14, y0, 58, 27, "F")
        pdf.set_xy(14, y0 + 2.5)
        pdf.set_text_color(255, 255, 255)
        pdf.set_font("VN" if pdf.has_vn else "Helvetica", "", 7.5)
        pdf.cell(58, 3.8, "KHUYẾN NGHỊ", align="C", new_x="LEFT", new_y="NEXT")

        rec_txt = a["rec"]
        font_sz = 13 if len(rec_txt) <= 10 else 10 if len(rec_txt) <= 18 else 8.5
        pdf.set_font("VN" if pdf.has_vn else "Helvetica", "B", font_sz)
        pdf.cell(58, 10, rec_txt, align="C", new_x="LEFT", new_y="NEXT")

        pdf.set_font("VN" if pdf.has_vn else "Helvetica", "", 7.8)
        total_txt = f"{a['total']:.0f}/100" if a["total"] is not None else "N/A"
        cov = a.get("coverage")
        cov_txt = f"  (độ phủ {cov:.0f}%)" if cov is not None and cov < 100 else ""
        pdf.cell(58, 4.2, f"Điểm tổng hợp: {total_txt}{cov_txt}", align="C")

        # 4 Hộp chỉ số bên phải
        boxes = [
            ("Giá hiện tại", _n(a["price"])),
            ("Giá mục tiêu", _n(a["target"])),
            ("Dư địa tăng", _n(a["upside"], 1, "%") if a["upside"] is not None else "N/A"),
            ("Cắt lỗ gợi ý", _n(a["stop"])),
        ]
        bx_w = 29.0
        bx_x = 75.0
        for lbl, val in boxes:
            pdf.set_fill_color(*LIGHT)
            pdf.rect(bx_x, y0, bx_w, 27, "F")
            pdf.set_xy(bx_x, y0 + 4.5)
            pdf.set_text_color(*GREY)
            pdf.set_font("VN" if pdf.has_vn else "Helvetica", "", 7.2)
            pdf.cell(bx_w, 3.8, lbl, align="C", new_x="LEFT", new_y="NEXT")

            pdf.set_xy(bx_x, y0 + 10.5)
            pdf.set_text_color(*NAVY)
            pdf.set_font("VN" if pdf.has_vn else "Helvetica", "B", 10.5)
            pdf.cell(bx_w, 8, val, align="C")
            bx_x += bx_w + 2.0

        pdf.set_text_color(0, 0, 0)
        pdf.set_y(y0 + 30)

        # 1. Luận điểm đầu tư sinh tự động
        pdf.h2("Luận điểm đầu tư (Mô hình lượng hóa sinh tự động)")
        pdf.set_font("VN" if pdf.has_vn else "Helvetica", "", 8.5)
        for c in a["comments"]:
            pdf.multi_cell(0, 4.6, "•  " + c, new_x="LMARGIN", new_y="NEXT")
            pdf.ln(0.4)

        # 2. Thẻ điểm 5 trụ cột với progress bar
        pdf.h2("Thẻ điểm 5 trụ cột lượng hóa")
        names_ = {
            "technical": "Kỹ thuật",
            "momentum": "Động lượng",
            "fundamental": "Cơ bản",
            "valuation": "Định giá",
            "risk": "Quản trị rủi ro",
        }
        wsum = sum(a["weights"].values()) or 100
        for k in ["fundamental", "valuation", "technical", "momentum", "risk"]:
            if k not in a["scores"]:
                continue
            s_val = a["scores"][k]
            w_pct = a["weights"].get(k, 20) / wsum * 100
            lbl = f"{names_.get(k, k)} ({w_pct:.0f}%)"

            pdf.set_font("VN" if pdf.has_vn else "Helvetica", "", 8.4)
            pdf.cell(46, 5.2, lbl)

            # Vẽ thanh tiến trình nền xám
            yb = pdf.get_y() + 1.2
            pdf.set_fill_color(226, 232, 240)
            pdf.rect(62, yb, 112, 3.0, "F")

            # Tô màu thanh tiến trình
            if s_val is not None:
                col = GREEN if s_val >= 65 else AMBER if s_val >= 45 else RED
                pdf.set_fill_color(*col)
                pdf.rect(62, yb, max(0.0, min(112.0, 112 * s_val / 100)), 3.0, "F")
                score_str = f"{s_val:.0f}/100"
            else:
                score_str = "Thiếu DL"

            pdf.set_x(176)
            pdf.set_font("VN" if pdf.has_vn else "Helvetica", "B", 8.4)
            pdf.cell(20, 5.2, score_str, align="R", new_x="LMARGIN", new_y="NEXT")

        # 3. Hiệu suất giá đa khung thời gian
        pdf.h2("Hiệu suất giá cổ phiếu")
        perf = [
            ("1 tháng", a.get("ret_1m"), "%"),
            ("3 tháng", a.get("ret_3m"), "%"),
            ("12 tháng", a.get("ret_1y"), "%"),
            ("vs VN-Index 6T", a.get("rs6"), " đ%"),
        ]
        card_w = 44.5
        for i, (lbl, v, suf) in enumerate(perf):
            pdf.set_fill_color(*LIGHT)
            pdf.set_font("VN" if pdf.has_vn else "Helvetica", "", 7.5)
            pdf.set_text_color(*GREY)
            pdf.cell(25, 5.8, "  " + lbl, fill=True)
            pdf.set_font("VN" if pdf.has_vn else "Helvetica", "B", 8.2)
            c_ret = GREY if v is None else GREEN if v >= 0 else RED
            pdf.set_text_color(*c_ret)
            pdf.cell(19.5, 5.8, _n(v, 1, suf) + " ", fill=True, align="R")
            if i < len(perf) - 1:
                pdf.cell(1.3, 5.8, "")
        pdf.ln(7.0)
        pdf.set_text_color(0, 0, 0)

        # 4. Tin tức & Bối cảnh thị trường
        pdf.h2("Bối cảnh thị trường & Tin tức tài chính")
        market_news = data.get("news_items", [])
        if market_news:
            pdf.set_font("VN" if pdf.has_vn else "Helvetica", "", 7.8)
            for item in market_news[:4]:
                s_tag = item.get("sentiment", "Trung tính")
                col = GREEN if "Tích cực" in s_tag else RED if "Tiêu cực" in s_tag else GREY
                d_str = item.get("date", "--")
                pdf.set_text_color(*GREY)
                pdf.cell(14, 4.6, d_str)
                pdf.set_text_color(*col)
                pdf.cell(18, 4.6, f"[{s_tag}]")
                pdf.set_text_color(0, 0, 0)
                title = str(item.get("title", ""))
                pdf.cell(0, 4.6, title if len(title) < 105 else title[:102] + "...", new_x="LMARGIN", new_y="NEXT")
        else:
            pdf.set_font("VN" if pdf.has_vn else "Helvetica", "", 8.0)
            pdf.set_text_color(*GREY)
            pdf.cell(0, 4.6, "Chưa thu thập được tin tức cho mã này tại thời điểm tạo báo cáo.", new_x="LMARGIN", new_y="NEXT")
            pdf.set_text_color(0, 0, 0)
        pdf.set_font("VN" if pdf.has_vn else "Helvetica", "", 6.8)
        pdf.set_text_color(*GREY)
        pdf.cell(0, 3.8, "Nguồn tin: Google News RSS / Vnstock / CafeF (phân loại sắc thái theo từ điển từ khóa).", new_x="LMARGIN", new_y="NEXT")
        pdf.set_text_color(0, 0, 0)

    def _render_technical(self, pdf: EquityReportPDF, data: dict, a: dict):
        ticker = data["ticker"]
        font = "VN" if pdf.has_vn else "Helvetica"

        # 1. Biểu đồ kỹ thuật 12 tháng
        pdf.h2("Phân tích kỹ thuật & Chỉ báo dao động")
        price_chart_img = _generate_price_chart(a["px"], ticker, a["target"], a["stop"])
        pdf.image(price_chart_img, x=14, w=182)
        pdf.ln(1.5)

        # 2. Hai biểu đồ nhỏ song song (Doanh thu & LNST + Sức mạnh tương đối)
        y_chart = pdf.get_y()
        fin_chart_img = _generate_fin_chart(a["fin"])
        rel_chart_img = _generate_rel_chart(a["px"], a["idx"])
        pdf.image(fin_chart_img, x=14, y=y_chart, w=89)
        pdf.image(rel_chart_img, x=107, y=y_chart, w=89)
        pdf.set_y(y_chart + 60)

        # 3. Bảng KQKD theo kỳ (số liệu thật, tối đa 6 kỳ gần nhất)
        pdf.h2("Kết quả kinh doanh theo kỳ báo cáo")
        fin = a["fin"]
        cols = [("Kỳ", 40), ("Doanh thu (tỷ)", 48), ("LNST (tỷ)", 48), ("Biên LN ròng", 46)]
        pdf.set_font(font, "B", 7.8)
        pdf.set_fill_color(*NAVY)
        pdf.set_text_color(255, 255, 255)
        for h, w in cols:
            pdf.cell(w, 5.2, h, align="C", fill=True)
        pdf.ln()
        pdf.set_text_color(0, 0, 0)
        pdf.set_font(font, "", 7.6)
        if fin is not None and not fin.empty:
            for idx, (_, r) in enumerate(fin.iterrows()):
                pdf.set_fill_color(*(LIGHT if idx % 2 == 0 else WHITE))
                rev, npat = r.get("revenue"), r.get("npat")
                rev_t = (rev / 1e9) if (rev is not None and pd.notna(rev) and abs(rev) > 1e7) else rev
                np_t = (npat / 1e9) if (npat is not None and pd.notna(npat) and abs(npat) > 1e7) else npat
                pdf.cell(40, 4.8, str(r.get("period", "--")), align="C", fill=True)
                pdf.cell(48, 4.8, _n(rev_t, 0), align="C", fill=True)
                pdf.cell(48, 4.8, _n(np_t, 0), align="C", fill=True)
                pdf.cell(46, 4.8, _n(r.get("net_margin"), 1, "%"), align="C", fill=True)
                pdf.ln()
            basis = a.get("rev_g_basis")
            if basis:
                pdf.set_font(font, "", 6.8)
                pdf.set_text_color(*GREY)
                pdf.cell(0, 4, f"Tăng trưởng doanh thu kỳ gần nhất: {_n(a.get('rev_g'), 1, '%')} – cơ sở so sánh: {basis}.",
                         new_x="LMARGIN", new_y="NEXT")
                pdf.set_text_color(0, 0, 0)
        else:
            pdf.cell(182, 5.0, "Không lấy được số liệu BCTC theo kỳ.", align="C")
            pdf.ln()

    def _render_peers(self, pdf: EquityReportPDF, data: dict, a: dict):
        ticker = data["ticker"]
        font = "VN" if pdf.has_vn else "Helvetica"
        peers = data.get("peers") or {}
        group_name = peers.get("group")
        if group_name:
            pdf.h2(f"So sánh với ngành: {group_name} ({peers.get('n', 0)} doanh nghiệp có số liệu)")
        else:
            pdf.h2("So sánh với ngành: chưa xác định được nhóm ngành")

        rel = a.get("rel_val", {})
        peer_rows = [
            ("ROE (%)", a.get("last_roe"), peers.get("roe"), "higher"),
            ("Biên LN ròng (%)", a.get("last_margin"), peers.get("net_margin"), "higher"),
            ("Nợ/VCSH (lần)", a.get("last_de"), peers.get("de"), "lower"),
            ("P/E (lần)", rel.get("pe"), peers.get("pe"), "cheaper"),
            ("P/B (lần)", rel.get("pb"), peers.get("pb"), "cheaper"),
        ]
        pdf.set_font(font, "B", 7.6)
        pdf.set_fill_color(226, 232, 240)
        for h, ww in [("Chỉ tiêu tài chính", 68), (ticker, 38), ("Trung vị ngành", 38), ("Đánh giá", 38)]:
            pdf.cell(ww, 5.0, h, fill=True, align="C")
        pdf.ln()

        pdf.set_font(font, "", 7.6)
        for idx, (lbl, me, med, mode) in enumerate(peer_rows):
            ok = me is not None and med is not None and not pd.isna(me) and not pd.isna(med)
            if not ok:
                col, tag = GREY, "Không đủ dữ liệu"
            elif mode == "higher":
                col, tag = (GREEN, "Tốt hơn ngành") if me > med else (RED, "Kém hơn ngành")
            elif mode == "lower":
                col, tag = (GREEN, "Tốt hơn ngành") if me < med else (RED, "Kém hơn ngành")
            else:
                col, tag = (GREEN, "Rẻ hơn ngành") if me < med else (RED, "Đắt hơn ngành")

            pdf.set_fill_color(*(LIGHT if idx % 2 == 0 else WHITE))
            pdf.cell(68, 4.8, "  " + lbl, fill=True)
            pdf.cell(38, 4.8, _n(me, 1), fill=True, align="C")
            pdf.cell(38, 4.8, _n(med, 1), fill=True, align="C")
            pdf.set_text_color(*col)
            pdf.cell(38, 4.8, tag, fill=True, align="C", new_x="LMARGIN", new_y="NEXT")
            pdf.set_text_color(0, 0, 0)

        if peers.get("peers"):
            pdf.set_font(font, "", 6.8)
            pdf.set_text_color(*GREY)
            pdf.multi_cell(0, 3.6, "Nhóm so sánh: " + ", ".join(peers["peers"])
                           + ". Trung vị chỉ công bố khi có ≥ 3 doanh nghiệp có số liệu hợp lệ.",
                           new_x="LMARGIN", new_y="NEXT")
            pdf.set_text_color(0, 0, 0)

    def _period_table(self, pdf: EquityReportPDF, title_col: str, rows: List[Tuple[str, List[str]]],
                      periods: List[str], label_w: float = 62.0):
        font = "VN" if pdf.has_vn else "Helvetica"
        col_w = (182 - label_w) / max(len(periods), 1)
        pdf.set_font(font, "B", 7.4)
        pdf.set_fill_color(*NAVY)
        pdf.set_text_color(255, 255, 255)
        pdf.cell(label_w, 5, " " + title_col, fill=True)
        for p in periods:
            pdf.cell(col_w, 5, p, align="C", fill=True)
        pdf.ln()
        pdf.set_text_color(0, 0, 0)
        pdf.set_font(font, "", 7.2)
        for i, (label, vals) in enumerate(rows):
            if label.startswith("§"):
                pdf.set_font(font, "B", 7.4)
                pdf.set_fill_color(226, 232, 240)
                pdf.cell(182, 4.6, " " + label[1:], fill=True, new_x="LMARGIN", new_y="NEXT")
                pdf.set_font(font, "", 7.2)
                continue
            pdf.set_fill_color(*(LIGHT if i % 2 == 0 else WHITE))
            pdf.cell(label_w, 4.4, " " + (label if len(label) <= 40 else label[:38] + "…"), fill=True)
            for v in vals:
                pdf.cell(col_w, 4.4, v, align="R", fill=True)
            pdf.ln()

    def _render_financials(self, pdf: EquityReportPDF, data: dict, a: dict):
        from data.financial_mapping import ITEMS_BY_KEY, PER_UNIT_KEYS, STATEMENT_ITEMS
        font = "VN" if pdf.has_vn else "Helvetica"
        fin = a.get("fin_wide")
        pdf.h2("Báo cáo tài chính nhiều năm (chuẩn hóa – đơn vị: tỷ đồng)")
        if fin is None or fin.empty:
            pdf.set_font(font, "", 8)
            pdf.cell(0, 5, "Không lấy được BCTC từ các nguồn dữ liệu.", new_x="LMARGIN", new_y="NEXT")
            return
        fin = fin.iloc[-6:]
        periods = [key_to_label(k) for k in fin.index]
        names = {"is": "KẾT QUẢ KINH DOANH", "bs": "CÂN ĐỐI KẾ TOÁN", "cf": "LƯU CHUYỂN TIỀN TỆ"}
        for st in ("is", "bs", "cf"):
            keys = [k for k in STATEMENT_ITEMS[st] if k in fin.columns and fin[k].notna().any()]
            if not keys:
                continue
            rows: List[Tuple[str, List[str]]] = [("§" + names[st], [])]
            for k in keys:
                per = k in PER_UNIT_KEYS
                rows.append((ITEMS_BY_KEY[k].label_vi,
                             [_n(v if per else (v / 1e9 if pd.notna(v) else v), 0) for v in fin[k].tolist()]))
            self._period_table(pdf, "Chỉ tiêu", rows, periods)
            pdf.ln(1.5)
        src = a.get("fin_sources")
        if src is not None and not src.empty:
            used = sorted({str(x) for x in pd.unique(src.values.ravel()) if isinstance(x, str)})
            pdf.set_font(font, "", 6.8)
            pdf.set_text_color(*GREY)
            pdf.multi_cell(0, 3.6, "Nguồn số liệu: " + ", ".join(used) +
                           ". Nguồn đứng trước trong chuỗi ưu tiên được dùng; ô thiếu được bù từ nguồn sau.",
                           new_x="LMARGIN", new_y="NEXT")
            pdf.set_text_color(0, 0, 0)

    def _render_ratios(self, pdf: EquityReportPDF, data: dict, a: dict):
        from analytics.financial_ratios import RATIO_META
        font = "VN" if pdf.has_vn else "Helvetica"
        summ = a.get("fin_summary") or {}
        ratios = summ.get("ratios")
        pdf.h2("Chỉ số tài chính – tính trực tiếp từ BCTC")
        if ratios is None or ratios.empty:
            pdf.set_font(font, "", 8)
            pdf.cell(0, 5, "Không đủ BCTC để tính chỉ số.", new_x="LMARGIN", new_y="NEXT")
            return
        r = ratios.iloc[-6:]
        periods = [key_to_label(k) for k in r.index]
        rows: List[Tuple[str, List[str]]] = []
        group = None
        for key, (label, grp, fmt, _) in RATIO_META.items():
            if key not in r.columns or r[key].isna().all() or fmt == "vnd" and key == "fcf":
                continue
            if grp != group:
                rows.append(("§" + grp.upper(), []))
                group = grp
            suf = {"%": "%", "x": "x", "days": ""}.get(fmt, "")
            d = 0 if fmt in ("days", "vnd") else (1 if fmt == "%" else 2)
            rows.append((label, [_n(v, d, suf) for v in r[key].tolist()]))
        self._period_table(pdf, "Chỉ số", rows, periods)

        # F-score, Z-score, định giá tại giá hiện tại
        pdf.ln(2)
        val = summ.get("valuation") or {}
        pio = summ.get("piotroski") or {}
        alt = summ.get("altman") or {}
        pdf.set_font(font, "B", 8.4)
        pdf.set_text_color(*NAVY)
        pdf.cell(0, 5, "Định giá tại giá hiện tại & điểm sức khỏe tài chính", new_x="LMARGIN", new_y="NEXT")
        pdf.set_text_color(0, 0, 0)
        pdf.set_font(font, "", 7.8)
        items = [
            ("P/E (EPS TTM)", _n(val.get("pe"), 1, "x")), ("P/B", _n(val.get("pb"), 2, "x")),
            ("P/S", _n(val.get("ps"), 2, "x")), ("EV/EBITDA", _n(val.get("ev_ebitda"), 1, "x")),
            ("Tỷ suất cổ tức", _n(val.get("dividend_yield"), 1, "%")),
            ("Vốn hóa (tỷ)", _n((val.get("market_cap") or 0) / 1e9 if val.get("market_cap") else None, 0)),
            ("Piotroski F-score", f"{pio.get('score')}/{pio.get('max')}" if pio.get("score") is not None else "N/A"),
            ("Altman Z''-score", f"{_n(alt.get('score'), 2)} – {alt.get('zone', '')}" if alt.get("score") is not None else "N/A"),
        ]
        for i, (lbl, v) in enumerate(items):
            pdf.set_fill_color(*LIGHT)
            pdf.cell(45, 5.2, " " + lbl, fill=True)
            pdf.cell(46, 5.2, v + " ", fill=True, align="R")
            if i % 2 == 1:          # 2 cặp (nhãn, giá trị) mỗi dòng
                pdf.ln(6)
        pdf.ln(2)
        pdf.set_font(font, "", 6.8)
        pdf.set_text_color(*GREY)
        pdf.multi_cell(0, 3.6, "Kỳ năm dùng số liệu cả năm; kỳ quý dùng 4 quý gần nhất (TTM). Tỷ số dòng/số dư dùng bình quân "
                       "đầu–cuối kỳ. F-score theo Piotroski (2000); Z''-score theo Altman (2005) cho thị trường mới nổi, "
                       "không áp dụng cho ngân hàng.", new_x="LMARGIN", new_y="NEXT")
        pdf.set_text_color(0, 0, 0)

    def _render_page_3(self, pdf: EquityReportPDF, data: dict, a: dict):
        font = "VN" if pdf.has_vn else "Helvetica"
        pdf.h2("Giải trình chấm điểm chi tiết từng trụ cột")
        pdf.set_font(font, "", 7.0)
        pdf.set_text_color(*GREY)
        pdf.multi_cell(0, 3.6, "Bảng dưới đây là đúng các thành phần mà hệ thống đã dùng để tính điểm. "
                       "Thành phần thiếu dữ liệu được loại khỏi cả tử số và mẫu số, không bị gán 0.",
                       new_x="LMARGIN", new_y="NEXT")
        pdf.set_text_color(0, 0, 0)
        pdf.ln(1)

        for title, group_checks in a.get("checks", []):
            if not group_checks:
                continue
            pdf.set_font(font, "B", 8.6)
            pdf.set_text_color(*NAVY)
            pdf.cell(0, 4.8, title, new_x="LMARGIN", new_y="NEXT")
            pdf.set_text_color(0, 0, 0)

            pdf.set_font(font, "B", 7.4)
            pdf.set_fill_color(226, 232, 240)
            headers = [("Tiêu chí định lượng", 62), ("Giá trị thực tế", 44), ("Đạt", 14), ("Điểm", 20), ("Ghi chú", 42)]
            for h, ww in headers:
                pdf.cell(ww, 4.6, h, fill=True, align="C")
            pdf.ln()

            pdf.set_font(font, "", 7.4)
            for c in group_checks:
                ok = "✓" if c.get("ok") is True else "✗" if c.get("ok") is False else "–"
                pdf.cell(62, 4.4, "  " + c.get("name", ""))
                pdf.cell(44, 4.4, str(c.get("value", "")), align="C")
                c_color = GREEN if c.get("ok") is True else RED if c.get("ok") is False else GREY
                pdf.set_text_color(*c_color)
                pdf.cell(14, 4.4, ok, align="C")
                pdf.set_text_color(0, 0, 0)
                pts = c.get("pts")
                pdf.cell(20, 4.4, f"{pts}/{c.get('max', 0)}" if pts is not None else f"–/{c.get('max', 0)}", align="C")
                note = str(c.get("note", ""))
                pdf.cell(42, 4.4, note if len(note) <= 30 else note[:28] + "…", align="C",
                         new_x="LMARGIN", new_y="NEXT")
            pdf.ln(1.5)

        # Thuyết minh phương pháp luận
        pdf.h2("Phương pháp luận định lượng (Quantitative Methodology)")
        pdf.set_font(font, "", 7.5)
        rel = a.get("rel_val", {})
        methods = [
            "Điểm cơ hội đầu tư tổng hợp = 25% Kỹ thuật + 20% Động lượng + 25% Cơ bản + 20% Định giá + 10% Quản trị rủi ro. "
            "Nhóm nào thiếu dữ liệu được loại ra và các trọng số còn lại được chuẩn hóa lại; độ phủ dữ liệu được ghi cạnh điểm tổng.",
            "Quy tắc khuyến nghị: MUA / CƠ HỘI NỔI BẬT khi điểm ≥ 80 và giá trị hợp lý cao hơn giá hiện tại; TÍCH CỰC khi 65–79; "
            "THEO DÕI / NẮM GIỮ khi 50–64; THẬN TRỌNG khi 35–49; BÁN / RỦI RO CAO khi < 35. Không có điểm tổng thì không đưa khuyến nghị.",
            f"Giá trị hợp lý = bình quân của EPS × P/E tham chiếu và BVPS × P/B tham chiếu. P/E tham chiếu: {rel.get('sector_pe_source', 'N/A')}; "
            f"P/B tham chiếu: {rel.get('sector_pb_source', 'N/A')}. Mô hình DCF chỉ hiển thị trên ứng dụng để tham khảo, không đưa vào giá trị hợp lý.",
            "Cắt lỗ gợi ý = Giá hiện tại − 2 × ATR(14). Không có dữ liệu ATR thì không đưa mức cắt lỗ.",
            "Tăng trưởng doanh thu/LNST so với cùng kỳ năm trước (YoY) khi xác định được kỳ báo cáo; nếu không, ghi rõ cơ sở so sánh.",
        ]
        for m in methods:
            pdf.multi_cell(0, 3.8, "•  " + m, new_x="LMARGIN", new_y="NEXT")
            pdf.ln(0.2)

        pdf.h2("Nguồn dữ liệu & Tuyên bố miễn trừ trách nhiệm (Disclaimer)")
        pdf.set_font(font, "", 7.2)
        pdf.set_text_color(*GREY)
        disclaimer = (
            "Dữ liệu thị trường và báo cáo tài chính được tổng hợp tự động từ Vnstock và DNSE. "
            "Báo cáo được lập hoàn toàn tự động bằng thuật toán định lượng phục vụ mục đích nghiên cứu học thuật. "
            "Các mục ghi N/A là do nguồn dữ liệu không cung cấp tại thời điểm tạo báo cáo. "
            "Báo cáo không cấu thành lời mời chào hay khuyến nghị mua/bán bất kỳ chứng khoán nào. "
            "Nhà đầu tư tự chịu trách nhiệm đối với quyết định của mình."
        )
        pdf.multi_cell(0, 3.8, disclaimer, new_x="LMARGIN", new_y="NEXT")

    # ─────────────────────────────────────────────────────────────────────────
    # Tiền xử lý dữ liệu – CHỈ dùng số liệu thật từ kết quả StockService.
    # Thiếu dữ liệu -> None -> hiển thị "N/A"; tuyệt đối không tự sinh số giả định.
    # ─────────────────────────────────────────────────────────────────────────

    _LABELS = {
        "fundamental": {
            "roe": ("ROE", "%"), "revenue_growth": ("Tăng trưởng doanh thu", "%"),
            "margin": ("Biên LN ròng", "%"), "debt": ("Nợ/VCSH", "x"),
            "cashflow": ("Dòng tiền HĐKD (CFO)", "cfo"),
        },
        "valuation": {"pe": ("P/E", "x"), "pb": ("P/B", "x")},
        "technical": {
            "ma_alignment": ("Giá so với SMA20/50/200", None), "rsi": ("RSI(14)", ""),
            "macd": ("MACD histogram", ""), "volume": ("Khối lượng tương đối", "x"),
            "bollinger": ("Vị trí dải Bollinger", None), "adx": ("ADX(14) + hướng DI", ""),
            "money_flow": ("Dòng tiền CMF / MFI / OBV", "mf"),
        },
        "momentum": {
            "short_momentum": ("Động lượng 5–10 phiên", "%"), "medium_momentum": ("Động lượng 20 phiên", "%"),
            "long_momentum": ("Động lượng 60–120 phiên", "%"),
            "relative_strength": ("Mạnh/yếu hơn VN-Index 60p", " đ%"), "rsi_zone": ("Vùng RSI", ""),
        },
        "risk": {
            "volatility": ("Biến động năm hóa", "vol"), "drawdown": ("Sụt giảm tối đa (MDD)", "mdd"),
            "beta": ("Beta so với VN-Index", ""), "debt_equity": ("Nợ/VCSH", "x"),
        },
    }

    def _component_rows(self, group: str, components: Dict[str, Any]) -> List[dict]:
        rows = []
        labels = self._LABELS.get(group, {})
        for key, comp in (components or {}).items():
            if not isinstance(comp, dict):
                continue
            name, fmt = labels.get(key, (key.replace("_", " ").title(), ""))
            pts, mx = comp.get("score"), comp.get("max", 0)
            v = comp.get("value")
            if pts is None:
                value, note, ok = "N/A", "Thiếu dữ liệu", None
            else:
                if fmt == "cfo":
                    cfo = comp.get("cfo")
                    value = _n(cfo / 1e9 if cfo is not None and abs(cfo) > 1e7 else cfo, 0, " tỷ")
                elif fmt == "mf":
                    parts = []
                    if comp.get("cmf") is not None:
                        parts.append(f"CMF {comp['cmf']:+.2f}")
                    if comp.get("mfi") is not None:
                        parts.append(f"MFI {comp['mfi']:.0f}")
                    if comp.get("obv_above_ma20") is not None:
                        parts.append("OBV>MA20" if comp["obv_above_ma20"] else "OBV<MA20")
                    value = " · ".join(parts) or "—"
                elif fmt == "vol":
                    value = _n(comp.get("annualized_vol"), 1, "%")
                elif fmt == "mdd":
                    value = _n(comp.get("max_drawdown_pct"), 1, "%")
                elif fmt is None:
                    value = "—"
                elif fmt == "x":
                    value = _n(v, 2, "x")
                else:
                    value = _n(v, 1, fmt)
                if key == "adx" and comp.get("direction"):
                    value += " ↑" if "Tăng" in comp["direction"] else " ↓"
                note = comp.get("basis") or comp.get("method") or comp.get("note") or ""
                note = (note.replace("YoY (cùng kỳ năm trước)", "YoY cùng kỳ")
                            .replace("So với trung vị ngành", "vs trung vị ngành")
                            .replace("Ngưỡng tuyệt đối thị trường", "Ngưỡng tuyệt đối"))
                ok = (pts / mx >= 0.5) if mx else None
            rows.append({"name": name, "value": value, "ok": ok, "pts": pts, "max": mx, "note": note})
        return rows

    @staticmethod
    def _fin_table(rp: Dict[str, Any], n: int = 6) -> pd.DataFrame:
        """Bảng KQKD theo kỳ từ chuỗi thật (revenue_series / net_profit_series)."""
        rev = rp.get("revenue_series") or []
        periods = rp.get("periods") or [f"Kỳ {i + 1}" for i in range(len(rev))]
        if not rev:
            return pd.DataFrame()
        np_map = dict(zip(rp.get("net_profit_periods") or [], rp.get("net_profit_series") or []))
        rows = []
        for per, r in list(zip(periods, rev))[-n:]:
            npat = np_map.get(per)
            margin = (npat / r * 100) if (npat is not None and r) else None
            rows.append({"period": per, "revenue": r, "npat": npat, "net_margin": margin})
        return pd.DataFrame(rows)

    @staticmethod
    def _level(score: Optional[float]) -> str:
        if score is None:
            return "chưa đủ dữ liệu"
        return "tích cực" if score >= 65 else "trung bình" if score >= 45 else "yếu"

    def _prepare_data(self, analysis: Dict[str, Any]) -> Tuple[dict, dict]:
        symbol = analysis.get("symbol", "UNKNOWN")
        company = analysis.get("company_info", {}) or {}
        name = company.get("company_name", company.get("short_name", company.get("name", symbol)))
        exchange = company.get("exchange", "")
        industry = company.get("industry", company.get("sector", ""))

        # ── Giá hiện tại & lịch sử giá (không có thì để None, không tự sinh) ──
        curr_p = analysis.get("current_price") or {}
        p_val = curr_p.get("price")
        tech = analysis.get("technical", {}) or {}
        px_df = tech.get("data") if tech.get("available") and isinstance(tech.get("data"), pd.DataFrame) else None
        if px_df is not None and px_df.empty:
            px_df = None
        if px_df is not None:
            px_df = px_df.copy()
            if p_val is None:
                p_val = float(px_df["close"].iloc[-1])

        # Chuẩn hóa đơn vị giá (quote < 1000 là nghìn đồng trên sàn VN)
        if p_val is not None and 0 < p_val < 1000.0:
            p_val = p_val * 1000.0
        if px_df is not None and px_df["close"].iloc[-1] < 1000.0 and (p_val or 0) >= 1000.0:
            for col in ["open", "high", "low", "close", "SMA_10", "SMA_20", "SMA_50", "SMA_100", "SMA_200",
                        "EMA_12", "EMA_26", "BB_upper", "BB_mid", "BB_lower", "ATR"]:
                if col in px_df.columns:
                    px_df[col] = px_df[col] * 1000.0

        # ── Định giá & giá trị hợp lý ──
        val_sec = analysis.get("valuation", {}) or {}
        val_score_data = val_sec.get("score", {}) if isinstance(val_sec, dict) else {}
        rel_val = val_score_data.get("relative_valuation", {}) if isinstance(val_score_data, dict) else {}
        target_p = rel_val.get("average_fair_value")
        if target_p is not None and target_p < 1000.0 and (p_val or 0) >= 1000.0:
            target_p = target_p * 1000.0
        upside = ((target_p - p_val) / p_val * 100.0) if (target_p and p_val) else None

        # ── Cắt lỗ = Giá − 2 × ATR (chỉ khi có ATR thật) ──
        stop_p = None
        if px_df is not None and "ATR" in px_df.columns and px_df["ATR"].notna().any() and p_val:
            stop_p = max(0.0, p_val - 2.0 * float(px_df["ATR"].dropna().iloc[-1]))

        # ── Điểm ──
        opp = analysis.get("opportunity_score", {}) or {}
        composite = opp.get("composite") if isinstance(opp.get("composite"), dict) else opp
        total_score = composite.get("score")
        coverage = composite.get("coverage_pct")
        sub_scores = opp.get("sub_scores", {}) if isinstance(opp.get("sub_scores"), dict) else {}

        def _sec_score(sec_name):
            sec = analysis.get(sec_name, {}) or {}
            sc = sec.get("score", {})
            return sc.get("score") if isinstance(sc, dict) else None

        weights = {"technical": 25, "momentum": 20, "fundamental": 25, "valuation": 20, "risk": 10}
        scores_dict = {
            "technical": sub_scores.get("technical", _sec_score("technical")),
            "momentum": sub_scores.get("momentum", _sec_score("momentum")),
            "fundamental": sub_scores.get("fundamental", _sec_score("fundamental")),
            "valuation": sub_scores.get("valuation", _sec_score("valuation")),
            "risk": sub_scores.get("risk"),
        }

        # ── Khuyến nghị ──
        if total_score is None:
            rec, rec_color = "CHƯA ĐỦ DỮ LIỆU", (120, 120, 120)
        elif total_score >= 80 and (upside is None or upside > 0):
            rec, rec_color = "MUA / CƠ HỘI NỔI BẬT", (16, 128, 64)
        elif total_score >= 65:
            rec, rec_color = "TÍCH CỰC / KHẢ QUAN", (42, 157, 143)
        elif total_score >= 50:
            rec, rec_color = "THEO DÕI / NẮM GIỮ", (200, 140, 0)
        elif total_score >= 35:
            rec, rec_color = "THẬN TRỌNG", (210, 105, 30)
        else:
            rec, rec_color = "BÁN / RỦI RO CAO", (190, 30, 45)

        # ── Hiệu suất giá (None khi không đủ phiên) ──
        ret_1m = ret_3m = ret_1y = None
        closes_s = px_df["close"].dropna() if px_df is not None else pd.Series(dtype=float)
        if len(closes_s) > 21:
            ret_1m = (closes_s.iloc[-1] / closes_s.iloc[-22] - 1) * 100
        if len(closes_s) > 63:
            ret_3m = (closes_s.iloc[-1] / closes_s.iloc[-64] - 1) * 100
        if len(closes_s) > 200:
            ret_1y = (closes_s.iloc[-1] / closes_s.iloc[0] - 1) * 100

        idx_df, rs6 = analysis.get("index_history"), None
        if px_df is not None:
            if idx_df is None:
                try:
                    from services.stock_service import StockService
                    idx_df = StockService(symbol, days=365).get_index_df()
                except Exception:
                    idx_df = None
            if idx_df is not None and not idx_df.empty and "close" in idx_df.columns:
                i_close = idx_df["close"].dropna()
                if len(i_close) > 120 and len(closes_s) > 120:
                    rs6 = ((closes_s.iloc[-1] / closes_s.iloc[-121] - 1)
                           - (i_close.iloc[-1] / i_close.iloc[-121] - 1)) * 100

        # ── Số liệu cơ bản thật ──
        fund_sec = analysis.get("fundamental", {}) or {}
        metrics = fund_sec.get("metrics", {}) if isinstance(fund_sec, dict) else {}
        rp = metrics.get("revenue_profit", {}) or {}
        rm = metrics.get("return_metrics", {}) or {}
        debt = metrics.get("debt", {}) or {}
        last_roe, last_roa = rm.get("roe"), rm.get("roa")
        last_margin = rp.get("net_margin")
        last_de = debt.get("debt_to_equity")
        rev_g, rev_g_basis = rp.get("revenue_yoy"), rp.get("revenue_growth_basis")
        fin_df = self._fin_table(rp)

        # ── Luận điểm đầu tư (văn bản sinh theo số liệu thật, tự điều chỉnh giọng theo điểm) ──
        rsi_last = None
        if px_df is not None and "RSI" in px_df.columns and px_df["RSI"].notna().any():
            rsi_last = float(px_df["RSI"].dropna().iloc[-1])
        trend = ((tech.get("signals") or {}).get("trend") or {}).get("name")

        def sc(k):
            v = scores_dict.get(k)
            return f"{v:.0f}/100" if v is not None else "N/A"

        comments = [
            f"Chất lượng doanh nghiệp {self._level(scores_dict['fundamental'])} ({sc('fundamental')}): "
            f"ROE {_n(last_roe, 1, '%')}, ROA {_n(last_roa, 1, '%')}, biên LN ròng {_n(last_margin, 1, '%')}, "
            f"tăng trưởng doanh thu {_n(rev_g, 1, '%')}" + (f" ({rev_g_basis})." if rev_g_basis else "."),
            f"Định giá {self._level(scores_dict['valuation'])} ({sc('valuation')}): P/E {_n(rel_val.get('pe'), 1, 'x')} "
            f"so với tham chiếu {_n(rel_val.get('sector_pe'), 1, 'x')}, P/B {_n(rel_val.get('pb'), 2, 'x')} "
            f"so với tham chiếu {_n(rel_val.get('sector_pb'), 2, 'x')}; giá trị hợp lý bình quân {_n(target_p, 0, ' VND')}"
            + (f" (chênh lệch {upside:+.1f}% so với giá hiện tại)." if upside is not None else "."),
            f"Kỹ thuật {self._level(scores_dict['technical'])} ({sc('technical')}): giá hiện tại {_n(p_val, 0, ' VND')}, "
            f"RSI {_n(rsi_last, 1)}" + (f", xu hướng {trend.lower()}" if trend else "")
            + (f"; cắt lỗ gợi ý {stop_p:,.0f} VND (2×ATR)." if stop_p else "."),
            f"Động lượng {self._level(scores_dict['momentum'])} ({sc('momentum')}): hiệu suất 3 tháng {_n(ret_3m, 1, '%')}, "
            f"12 tháng {_n(ret_1y, 1, '%')}" + (f", chênh lệch với VN-Index 6 tháng {rs6:+.1f} điểm %." if rs6 is not None else ".")
            + f" Điểm rủi ro {sc('risk')}.",
            (f"Tổng hợp: khuyến nghị {rec} với điểm {total_score:.0f}/100"
             + (f" (tính trên {coverage:.0f}% trọng số do thiếu dữ liệu)." if coverage is not None and coverage < 100 else "."))
            if total_score is not None else
            "Tổng hợp: chưa đủ dữ liệu để tính điểm tổng và đưa ra khuyến nghị.",
        ]

        # ── Giải trình điểm: lấy ĐÚNG các thành phần đã dùng để chấm ──
        def comps(sec_name):
            sec = analysis.get(sec_name, {}) or {}
            sc_ = sec.get("score", {})
            return sc_.get("components", {}) if isinstance(sc_, dict) else {}

        risk_comps = ((opp.get("risk_detail") or {}).get("components")) or {}
        checks = [
            (f"1. Phân tích cơ bản – {sc('fundamental')}", self._component_rows("fundamental", comps("fundamental"))),
            (f"2. Định giá – {sc('valuation')}", self._component_rows("valuation", comps("valuation"))),
            (f"3. Kỹ thuật – {sc('technical')}", self._component_rows("technical", comps("technical"))),
            (f"4. Động lượng – {sc('momentum')}", self._component_rows("momentum", comps("momentum"))),
            (f"5. Quản trị rủi ro – {sc('risk')}", self._component_rows("risk", risk_comps)),
        ]

        # ── Tin tức thật (nếu StockService/trang PDF đã thu thập) ──
        sent_map = {"positive": "Tích cực", "negative": "Tiêu cực", "neutral": "Trung tính"}
        news_items = []
        for it in (analysis.get("news") or [])[:4]:
            d = it.get("timestamp_dt") or it.get("date") or it.get("published")
            if hasattr(d, "strftime"):
                d = d.strftime("%d/%m")
            news_items.append({
                "date": str(d)[:10] if d else "--",
                "sentiment": sent_map.get(it.get("sentiment"), it.get("sentiment") or "Trung tính"),
                "title": it.get("title", ""),
            })

        data_meta = {
            "ticker": symbol,
            "name": name,
            "exchange": exchange,
            "industry": industry,
            "last_session": datetime.now().strftime("%d/%m/%Y"),
            "fetched_at": datetime.now().strftime("%H:%M %d/%m/%Y"),
            "data_source": "Vnstock / DNSE / BCTC Niêm Yết",
            "peers": analysis.get("peers") or {},
            "news_items": news_items,
        }

        analysis_dict = {
            "price": p_val,
            "target": target_p,
            "upside": upside,
            "stop": stop_p,
            "total": total_score,
            "coverage": coverage,
            "rec": rec,
            "rec_color": rec_color,
            "scores": scores_dict,
            "weights": weights,
            "comments": comments,
            "ret_1m": ret_1m,
            "ret_3m": ret_3m,
            "ret_1y": ret_1y,
            "rs6": rs6,
            "px": px_df,
            "idx": idx_df,
            "fin": fin_df,
            "rel_val": rel_val,
            "last_roe": last_roe,
            "last_margin": last_margin,
            "last_de": last_de,
            "rev_g": rev_g,
            "rev_g_basis": rev_g_basis,
            "checks": checks,
            "fin_wide": (analysis.get("financials") or {}).get("data"),
            "fin_sources": (analysis.get("financials") or {}).get("sources"),
            "fin_summary": analysis.get("financial_summary"),
        }
        return data_meta, analysis_dict
