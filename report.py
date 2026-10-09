"""
TẦNG 3: XUẤT BÁO CÁO PDF (format kiểu báo cáo công ty chứng khoán)
"""
from __future__ import annotations

import io
import os
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
from fpdf import FPDF

NAVY = (14, 42, 82)
GREY = (110, 110, 110)
LIGHT = (240, 243, 248)


def _font_paths():
    """Font có dấu tiếng Việt: ưu tiên Arial (Windows), dự phòng DejaVu đi kèm matplotlib."""
    win = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts"
    if (win / "arial.ttf").exists() and (win / "arialbd.ttf").exists():
        return str(win / "arial.ttf"), str(win / "arialbd.ttf")
    mpl = Path(matplotlib.get_data_path()) / "fonts" / "ttf"
    return str(mpl / "DejaVuSans.ttf"), str(mpl / "DejaVuSans-Bold.ttf")


# ---------------------------------------------------------------------
# Biểu đồ
# ---------------------------------------------------------------------

def _png(fig) -> io.BytesIO:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=160, bbox_inches="tight")
    plt.close(fig)
    buf.seek(0)
    return buf


def chart_price(a, ticker):
    px = a["px"].tail(252)
    fig, (ax, ax2) = plt.subplots(2, 1, figsize=(9, 4.6), sharex=True,
                                  gridspec_kw={"height_ratios": [3, 1]})
    ax.plot(px["time"], px["close"], color="#0e2a52", lw=1.4, label="Giá đóng cửa")
    ax.plot(px["time"], px["ma50"], color="#e08a00", lw=1, label="MA50")
    ax.plot(px["time"], px["ma200"], color="#2a9d8f", lw=1, label="MA200")
    if a["target"]:
        ax.axhline(a["target"], color="#108040", ls="--", lw=1, label="Giá mục tiêu")
    if a["stop"]:
        ax.axhline(a["stop"], color="#be1e2d", ls=":", lw=1, label="Cắt lỗ (2×ATR)")
    ax.set_title(f"{ticker} – Diễn biến giá 12 tháng", fontsize=11, loc="left")
    ax.legend(fontsize=7, loc="upper left", ncol=5, frameon=False)
    ax.grid(alpha=.25)
    ax2.plot(px["time"], px["rsi"], color="#5a5a5a", lw=1)
    ax2.axhspan(30, 70, color="#0e2a52", alpha=.06)
    ax2.set_ylabel("RSI", fontsize=8)
    ax2.set_ylim(0, 100)
    ax2.grid(alpha=.25)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False); ax2.spines[s].set_visible(False)
    return _png(fig)


def chart_fin(a):
    fin = a["fin"]
    fig, ax = plt.subplots(figsize=(4.4, 3))
    x = range(len(fin))
    ax.bar([i - .2 for i in x], fin["revenue"], width=.4, color="#0e2a52", label="Doanh thu")
    ax.bar([i + .2 for i in x], fin["npat"], width=.4, color="#e08a00", label="LNST")
    ax.set_xticks(list(x), fin["year"].astype(str))
    ax.set_title("Doanh thu & LNST (tỷ đồng)", fontsize=10, loc="left")
    ax.legend(fontsize=7, frameon=False)
    ax.grid(axis="y", alpha=.25)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    return _png(fig)


def chart_rel(a):
    px, idx = a["px"].tail(126), a["idx"]
    idx = idx[idx["time"] >= px["time"].iloc[0]]
    fig, ax = plt.subplots(figsize=(4.4, 3))
    ax.plot(px["time"], px["close"] / px["close"].iloc[0] * 100, color="#0e2a52", lw=1.4, label="Cổ phiếu")
    ax.plot(idx["time"], idx["close"] / idx["close"].iloc[0] * 100, color="#9a9a9a", lw=1.2, label="VN-Index")
    ax.set_title("Sức mạnh tương đối 6 tháng (gốc = 100)", fontsize=10, loc="left")
    ax.legend(fontsize=7, frameon=False)
    ax.grid(alpha=.25)
    ax.tick_params(axis="x", labelsize=7, rotation=30)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    return _png(fig)


# ---------------------------------------------------------------------
# PDF
# ---------------------------------------------------------------------

def _n(x, d=0, suf=""):
    return "N/A" if x is None or pd.isna(x) else f"{x:,.{d}f}{suf}"


class Report(FPDF):
    def __init__(self, data):
        super().__init__(format="A4")
        self.data = data
        reg, bold = _font_paths()
        self.add_font("VN", "", reg)
        self.add_font("VN", "B", bold)
        self.set_auto_page_break(True, margin=16)
        self.set_margins(14, 14, 14)

    def header(self):
        self.set_fill_color(*NAVY)
        self.rect(0, 0, 210, 9, "F")
        self.set_xy(14, 2)
        self.set_font("VN", "B", 8)
        self.set_text_color(255, 255, 255)
        self.cell(0, 5, "HỆ THỐNG PHÂN TÍCH CƠ HỘI ĐẦU TƯ CỔ PHIẾU  |  BÁO CÁO TỰ ĐỘNG")
        self.set_xy(14, 13)
        self.set_text_color(0, 0, 0)

    def footer(self):
        self.set_y(-12)
        self.set_font("VN", "", 7)
        self.set_text_color(*GREY)
        self.cell(0, 5, f"Dữ liệu: DNSE (giá), Google News (tin), vnfinancialdata/arminer (BCTC)  |  Phiên cuối: "
                        f"{self.data['last_session']}  |  Tạo lúc {self.data['fetched_at']}", align="L")
        self.cell(0, 5, f"Trang {self.page_no()}/{{nb}}", align="R")

    def h2(self, txt):
        self.ln(2)
        self.set_font("VN", "B", 11)
        self.set_text_color(*NAVY)
        self.cell(0, 7, txt, new_x="LMARGIN", new_y="NEXT")
        self.set_draw_color(*NAVY)
        self.line(self.l_margin, self.get_y(), 196, self.get_y())
        self.ln(2)
        self.set_text_color(0, 0, 0)

    def kv_table(self, rows, widths=(55, 35)):
        self.set_font("VN", "", 8.5)
        for i, (k, v) in enumerate(rows):
            self.set_fill_color(*(LIGHT if i % 2 == 0 else (255, 255, 255)))
            self.cell(widths[0], 6, k, fill=True)
            self.cell(widths[1], 6, v, fill=True, align="R", new_x="LMARGIN", new_y="NEXT")


def market_section(pdf, mk, limit=8):
    """Mục 'Bối cảnh thị trường': tâm lý theo chủ đề + tiêu đề tin (dùng chung cho PDF từng mã và PDF sàng lọc)."""
    mk = mk or {}
    pdf.h2("Bối cảnh thị trường (tin tức 7 ngày)")
    items = mk.get("items")
    if items is None or not len(items):
        pdf.set_font("VN", "", 8.5)
        pdf.cell(0, 5, f"Không lấy được tin thị trường ({mk.get('source', 'N/A')}).", new_x="LMARGIN", new_y="NEXT")
        return
    sc = mk["score"]
    pdf.set_font("VN", "B", 9)
    pdf.set_text_color(*((16, 128, 64) if sc > 0.2 else (190, 30, 45) if sc < -0.2 else (170, 115, 0)))
    pdf.cell(0, 5.5, f"Chỉ số tâm lý thị trường: {sc:+.2f} "
                     f"({'tích cực' if sc > 0.2 else 'tiêu cực' if sc < -0.2 else 'trung tính'})",
             new_x="LMARGIN", new_y="NEXT")
    pdf.set_text_color(0, 0, 0)
    bt = mk.get("by_topic", {})
    if bt:
        pdf.set_font("VN", "", 8)
        pdf.cell(0, 5, "Theo chủ đề:  " + "   |   ".join(f"{k}: {v:+.2f}" for k, v in bt.items()),
                 new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("VN", "", 8)
    for _, r in items.head(limit).iterrows():
        s_ = r["sentiment"]
        col = (16, 128, 64) if s_ > 0 else (190, 30, 45) if s_ < 0 else GREY
        pdf.set_text_color(*GREY)
        pdf.cell(20, 5, str(r.get("topic", "")))
        pdf.set_text_color(*col)
        pdf.cell(6, 5, "▲" if s_ > 0 else "▼" if s_ < 0 else "•")
        pdf.set_text_color(0, 0, 0)
        title = str(r["title"])
        pdf.cell(0, 5, title if len(title) < 100 else title[:97] + "...", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("VN", "", 7)
    pdf.set_text_color(*GREY)
    pdf.cell(0, 4, f"Nguồn: {mk.get('source')}. Tâm lý thị trường chiếm 30% điểm trụ Tin tức.",
             new_x="LMARGIN", new_y="NEXT")
    pdf.set_text_color(0, 0, 0)


def build_pdf(data: dict, a: dict, out_path: str) -> str:
    t = data["ticker"]
    pdf = Report(data)
    pdf.alias_nb_pages()

    # ========================= TRANG 1 =========================
    pdf.add_page()
    if data.get("demo"):
        pdf.set_font("VN", "B", 9)
        pdf.set_text_color(190, 30, 45)
        pdf.multi_cell(0, 5, "CHẾ ĐỘ KIỂM THỬ: BCTC là số liệu thật, nhưng GIÁ và TIN TỨC là MÔ PHỎNG – định giá, động lượng và khuyến nghị không phản ánh thực tế.",
                       new_x="LMARGIN", new_y="NEXT")
        pdf.set_text_color(0, 0, 0)

    pdf.set_font("VN", "B", 22)
    pdf.set_text_color(*NAVY)
    pdf.cell(0, 11, t, new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("VN", "", 10)
    pdf.set_text_color(*GREY)
    pdf.cell(0, 5, f"{data['name']}" + (f"  •  {data['industry']}" if data.get("industry") else ""),
             new_x="LMARGIN", new_y="NEXT")
    pdf.ln(3)

    # Hộp khuyến nghị
    y0 = pdf.get_y()
    pdf.set_fill_color(*a["rec_color"])
    pdf.rect(14, y0, 60, 30, "F")
    pdf.set_xy(14, y0 + 3)
    pdf.set_text_color(255, 255, 255)
    pdf.set_font("VN", "", 8)
    pdf.cell(60, 4, "KHUYẾN NGHỊ", align="C", new_x="LEFT", new_y="NEXT")
    pdf.set_font("VN", "B", 15 if len(a["rec"]) < 8 else 11)
    pdf.cell(60, 10, a["rec"], align="C", new_x="LEFT", new_y="NEXT")
    pdf.set_font("VN", "", 8)
    pdf.cell(60, 5, f"Điểm tổng hợp: {a['total']:.0f}/100", align="C")

    # Các ô số liệu chính
    boxes = [
        ("Giá hiện tại", _n(a["price"])),
        ("Giá mục tiêu", _n(a["target"])),
        ("Dư địa", _n(a["upside"], 1, "%")),
        ("Cắt lỗ gợi ý", _n(a["stop"])),
    ]
    x = 78
    for lbl, val in boxes:
        pdf.set_fill_color(*LIGHT)
        pdf.rect(x, y0, 28.5, 30, "F")
        pdf.set_xy(x, y0 + 6)
        pdf.set_text_color(*GREY)
        pdf.set_font("VN", "", 7.5)
        pdf.cell(28.5, 4, lbl, align="C", new_x="LEFT", new_y="NEXT")
        pdf.set_text_color(*NAVY)
        pdf.set_font("VN", "B", 11)
        pdf.cell(28.5, 9, val, align="C")
        x += 29.5
    pdf.set_text_color(0, 0, 0)
    pdf.set_y(y0 + 34)

    # Luận điểm
    pdf.h2("Luận điểm đầu tư (sinh tự động)")
    pdf.set_font("VN", "", 9)
    for c in a["comments"]:
        pdf.multi_cell(0, 5, "•  " + c, new_x="LMARGIN", new_y="NEXT")
        pdf.ln(0.5)

    # Bảng điểm
    pdf.h2("Thẻ điểm 4 trụ cột")
    names_ = {"quality": "Chất lượng DN", "valuation": "Định giá", "momentum": "Động lượng giá", "news": "Tin tức"}
    wsum = sum(a["weights"].values())
    for k in a["scores"]:
        lbl = f"{names_[k]} ({a['weights'][k] / wsum * 100:.0f}%)"
        s = a["scores"][k]
        pdf.set_font("VN", "", 9)
        pdf.cell(48, 6, lbl)
        yb = pdf.get_y() + 1.5
        pdf.set_fill_color(225, 228, 235)
        pdf.rect(64, yb, 110, 3.5, "F")
        col = (16, 128, 64) if s >= 70 else (200, 140, 0) if s >= 45 else (190, 30, 45)
        pdf.set_fill_color(*col)
        pdf.rect(64, yb, 110 * s / 100, 3.5, "F")
        pdf.set_x(178)
        pdf.set_font("VN", "B", 9)
        pdf.cell(18, 6, f"{s:.0f}/100", align="R", new_x="LMARGIN", new_y="NEXT")

    pdf.h2("Hiệu suất giá")
    perf = [("1 tháng", a["ret_1m"], "%"), ("3 tháng", a["ret_3m"], "%"), ("12 tháng", a["ret_1y"], "%"),
            ("So với VN-Index 6T", a["rs6"], " đ%")]
    for i, (lbl, v, suf) in enumerate(perf):
        pdf.set_fill_color(*LIGHT)
        pdf.set_font("VN", "", 7.5)
        pdf.set_text_color(*GREY)
        pdf.cell(26, 6, lbl, fill=True)
        pdf.set_font("VN", "B", 8.5)
        pdf.set_text_color(*((16, 128, 64) if (v or 0) >= 0 else (190, 30, 45)))
        pdf.cell(18.5, 6, _n(v, 1, suf), fill=True, align="R")
        pdf.cell(1, 6, "")
    pdf.ln(7)
    pdf.set_text_color(0, 0, 0)

    nw = data.get("news") or {}
    pdf.h2("Tin tức & sự kiện gần đây")
    items = nw.get("items")
    if items is not None and len(items):
        pdf.set_font("VN", "", 8)
        for _, r in items.head(5).iterrows():
            sc = r["sentiment"]
            col, tag = ((16, 128, 64), "Tích cực") if sc > 0 else ((190, 30, 45), "Tiêu cực") if sc < 0 else (GREY, "Trung tính")
            d = r["date"].strftime("%d/%m") if pd.notna(r["date"]) else "--"
            pdf.set_text_color(*GREY)
            pdf.cell(12, 5, d)
            pdf.set_text_color(*col)
            pdf.cell(18, 5, tag)
            pdf.set_text_color(0, 0, 0)
            title = str(r["title"])
            pdf.cell(0, 5, title if len(title) < 105 else title[:102] + "...", new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("VN", "", 7)
        pdf.set_text_color(*GREY)
        pdf.cell(0, 4, f"Nguồn tin: {nw.get('source')}. Cảm xúc chấm tự động theo từ điển từ khoá tiếng Việt.",
                 new_x="LMARGIN", new_y="NEXT")
        pdf.set_text_color(0, 0, 0)
    else:
        pdf.set_font("VN", "", 8.5)
        pdf.cell(0, 5, f"Không lấy được tin tức ({nw.get('source', 'N/A')}).", new_x="LMARGIN", new_y="NEXT")

    market_section(pdf, data.get("market_news"), limit=5)

    # ========================= TRANG 2 =========================
    pdf.add_page()
    pdf.h2("Phân tích kỹ thuật")
    pdf.image(chart_price(a, t), x=14, w=182)
    pdf.ln(2)
    yc = pdf.get_y()
    pdf.image(chart_fin(a), x=14, y=yc, w=89)
    pdf.image(chart_rel(a), x=107, y=yc, w=89)
    pdf.set_y(yc + 64)

    pdf.h2("Chỉ số tài chính theo năm")
    fin = a["fin"]
    cols = [("Năm", "year", 0, ""), ("DT (tỷ)", "revenue", 0, ""), ("LNST (tỷ)", "npat", 0, ""),
            ("ROE", "roe", 1, "%"), ("ROA", "roa", 1, "%"), ("Biên LN", "net_margin", 1, "%"),
            ("Nợ/VCSH", "de", 2, ""), ("P/E", "pe", 1, ""), ("P/B", "pb", 1, "")]
    w = 182 / len(cols)
    pdf.set_font("VN", "B", 8)
    pdf.set_fill_color(*NAVY)
    pdf.set_text_color(255, 255, 255)
    for h, *_ in cols:
        pdf.cell(w, 6, h, align="C", fill=True)
    pdf.ln()
    pdf.set_text_color(0, 0, 0)
    pdf.set_font("VN", "", 8)
    for i, (_, r) in enumerate(fin.iterrows()):
        pdf.set_fill_color(*(LIGHT if i % 2 == 0 else (255, 255, 255)))
        for _, key, d, suf in cols:
            v = r.get(key)
            txt = str(int(v)) if key == "year" else _n(v, d, suf)
            pdf.cell(w, 5.5, txt, align="C", fill=True)
        pdf.ln()

    pr = data.get("peers") or {}
    if pr:
        pdf.h2(f"So sánh với ngành: {pr['group']} ({pr['n']} doanh nghiệp)")
        last = fin.iloc[-1]
        rev_g = a["rev_g"]
        rows = [("ROE (%)", last.get("roe"), pr["roe"]), ("Biên LN ròng (%)", last.get("net_margin"), pr["net_margin"]),
                ("Tăng trưởng doanh thu (%)", rev_g, pr["rev_g"]), ("Nợ/VCSH (lần)", last.get("de"), pr["de"])]
        pdf.set_font("VN", "B", 8)
        pdf.set_fill_color(225, 228, 235)
        for h, ww in [("Chỉ tiêu", 70), (t, 37), ("Trung vị ngành", 37), ("Đánh giá", 38)]:
            pdf.cell(ww, 5.5, h, fill=True, align="C")
        pdf.ln()
        pdf.set_font("VN", "", 8)
        for i, (lbl, me, med) in enumerate(rows):
            better = None if pd.isna(me) or pd.isna(med) else bool(me < med if "Nợ" in lbl else me > med)
            pdf.set_fill_color(*(LIGHT if i % 2 == 0 else (255, 255, 255)))
            pdf.cell(70, 5.5, lbl, fill=True)
            pdf.cell(37, 5.5, _n(me, 1), fill=True, align="C")
            pdf.cell(37, 5.5, _n(med, 1), fill=True, align="C")
            pdf.set_text_color(*((16, 128, 64) if better else (190, 30, 45) if better is False else GREY))
            pdf.cell(38, 5.5, "Tốt hơn ngành" if better else "Kém hơn ngành" if better is False else "N/A",
                     fill=True, align="C", new_x="LMARGIN", new_y="NEXT")
            pdf.set_text_color(0, 0, 0)

    # ========================= TRANG 3 =========================
    pdf.add_page()
    pdf.h2("Giải trình chấm điểm chi tiết")
    names = {"quality": "1. Chất lượng doanh nghiệp", "valuation": "2. Định giá", "momentum": "3. Động lượng & thị trường"}
    for k, title in names.items():
        pdf.set_font("VN", "B", 9.5)
        pdf.set_text_color(*NAVY)
        pdf.cell(0, 6, title, new_x="LMARGIN", new_y="NEXT")
        pdf.set_text_color(0, 0, 0)
        pdf.set_font("VN", "B", 8)
        pdf.set_fill_color(225, 228, 235)
        for h, ww in [("Tiêu chí", 72), ("Giá trị", 45), ("Đạt", 18), ("Điểm", 20), ("Ghi chú", 27)]:
            pdf.cell(ww, 5.5, h, fill=True, align="C")
        pdf.ln()
        pdf.set_font("VN", "", 8)
        for c in a["checks"][k]:
            ok = "–" if c["ok"] is None else ("✓" if c["ok"] else "✗")
            pdf.cell(72, 5.5, c["name"])
            pdf.cell(45, 5.5, c["value"], align="C")
            pdf.set_text_color(*((16, 128, 64) if c["ok"] else (190, 30, 45) if c["ok"] is False else GREY))
            pdf.cell(18, 5.5, ok, align="C")
            pdf.set_text_color(0, 0, 0)
            pdf.cell(20, 5.5, f"{c['pts']}/{c['max']}", align="C")
            pdf.cell(27, 5.5, c["note"], align="C", new_x="LMARGIN", new_y="NEXT")
        pdf.ln(2)

    pdf.h2("Phương pháp")
    pdf.set_font("VN", "", 8.5)
    method = [
        "Điểm tổng hợp = 35% Chất lượng + 30% Định giá + 25% Động lượng + 10% Tin tức (khi không có tin, trọng số chia lại theo tỷ lệ). Khuyến nghị: MUA khi ≥ 70 điểm và giá mục tiêu cao hơn giá hiện tại; THEO DÕI/NẮM GIỮ khi 50–70; TRÁNH/BÁN khi < 50.",
        "Điểm tin tức = (cảm xúc tổng hợp + 1) × 50, trong đó cảm xúc tổng hợp = 70% tin doanh nghiệp (90 ngày) + 30% tin thị trường chung (7 ngày: VN-Index, khối ngoại, vĩ mô, nâng hạng); cảm xúc mỗi bài ∈ [−1, 1] theo từ điển từ khoá có trọng số.",
        "So sánh ngành: trung vị ROE, biên LN, tăng trưởng doanh thu, nợ/VCSH của các DN cùng ngành ICB cấp 3, tính từ cùng bộ BCTC.",
        "P/E, P/B lịch sử = giá đóng cửa phiên cuối mỗi năm / EPS, BVPS năm đó; ROE, ROA tính trên vốn chủ sở hữu và tổng tài sản bình quân.",
        "Giá mục tiêu = bình quân (EPS × P/E trung vị lịch sử; BVPS × P/B trung vị lịch sử). Loại các năm P/E âm hoặc > 60x, P/B > 15x; dư địa giới hạn ±50%. Giá dùng là giá điều chỉnh, nên EPS, BVPS các năm được quy về số cổ phiếu hiện tại.",
        "Cắt lỗ gợi ý = Giá hiện tại − 2 × ATR(14). Chỉ báo kỹ thuật: MA50, MA200, RSI(14), sức mạnh tương đối 6 tháng so với VN-Index.",
        "Với ngân hàng/công ty tài chính (Nợ/VCSH > 4), tiêu chí đòn bẩy được miễn và ngưỡng ROA hạ còn 1% do đặc thù ngành.",
    ]
    for mtxt in method:
        pdf.multi_cell(0, 4.6, "•  " + mtxt, new_x="LMARGIN", new_y="NEXT")
        pdf.ln(0.5)

    pdf.h2("Kiểm soát chất lượng dữ liệu")
    pdf.set_font("VN", "", 8)
    chk = data.get("check")
    if chk is not None and len(chk):
        pdf.multi_cell(0, 4.4, "Đối chiếu chéo BCTC nguồn chính với vnstock (chênh lệch > 5% được tô đỏ):",
                       new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("VN", "B", 8)
        pdf.set_fill_color(225, 228, 235)
        for h, ww in [("Năm", 20), ("Chỉ tiêu", 50), ("Nguồn chính", 40), ("vnstock", 40), ("Chênh lệch", 32)]:
            pdf.cell(ww, 5.5, h, fill=True, align="C")
        pdf.ln()
        pdf.set_font("VN", "", 8)
        for _, r in chk.iterrows():
            pdf.cell(20, 5, str(r["year"]), align="C")
            pdf.cell(50, 5, r["metric"])
            pdf.cell(40, 5, _n(r["main"], 1), align="C")
            pdf.cell(40, 5, _n(r["vnstock"], 1), align="C")
            pdf.set_text_color(*((190, 30, 45) if abs(r["diff"]) > 5 else (16, 128, 64)))
            pdf.cell(32, 5, f"{r['diff']:+.1f}%", align="C", new_x="LMARGIN", new_y="NEXT")
            pdf.set_text_color(0, 0, 0)
        pdf.ln(1)
    else:
        pdf.multi_cell(0, 4.4, "Chưa đối chiếu chéo được với nguồn thứ hai trong lần chạy này.", new_x="LMARGIN", new_y="NEXT")
    for nt in data.get("notes", []):
        pdf.multi_cell(0, 4.4, "•  " + nt, new_x="LMARGIN", new_y="NEXT")

    pdf.h2("Nguồn dữ liệu & Miễn trừ trách nhiệm")
    pdf.set_font("VN", "", 8)
    pdf.set_text_color(*GREY)
    pdf.multi_cell(0, 4.4,
        f"Giá: {data.get('price_source', data['source'])}, phiên gần nhất {data['last_session']}. "
        f"BCTC: {data.get('fin_source', data['source'])}. Ngành ICB: danh mục FiinPro/Vietcap IQ của repo "
        f"vn-annual-report-miner. Tạo lúc {data['fetched_at']}. Số liệu tài chính theo năm, đơn vị tỷ đồng; giá tính bằng đồng. "
        "Báo cáo được tạo tự động cho mục đích học tập, không phải khuyến nghị đầu tư. Nhà đầu tư cần tự kiểm chứng "
        "số liệu với báo cáo tài chính gốc trước khi ra quyết định.")

    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    pdf.output(out_path)
    return out_path
