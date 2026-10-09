"""
QUÉT THỊ TRƯỜNG: chấm điểm cả rổ cổ phiếu -> xếp hạng -> PDF tổng hợp + PDF chi tiết top N
    python screener.py                       # quét VN30
    python screener.py --group HOSE          # quét toàn sàn HOSE (lâu, do giới hạn API)
    python screener.py --group VN30 --top 5  # kèm PDF chi tiết cho 5 mã điểm cao nhất
    python screener.py --tickers FPT,HPG,MWG # tự chọn danh sách
    python screener.py --demo                # dữ liệu mô phỏng
Nhóm hỗ trợ: VN30, VN100, VNMidCap, VNSmallCap, HNX30, HOSE, HNX, UPCOM...
"""
from __future__ import annotations

import argparse
import datetime as dt
import time
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

from analyzer import load_data, analyze
from report import Report, build_pdf, market_section, _png, _n, NAVY, LIGHT, GREY

# Danh sách dự phòng khi không lấy được rổ từ API (cần đối chiếu rổ VN30 kỳ hiện hành)
VN30_FALLBACK = ["ACB", "BCM", "BID", "BVH", "CTG", "FPT", "GAS", "GVR", "HDB", "HPG",
                 "LPB", "MBB", "MSN", "MWG", "PLX", "SAB", "SHB", "SSB", "SSI", "STB",
                 "TCB", "TPB", "VCB", "VHM", "VIB", "VIC", "VJC", "VNM", "VPB", "VRE"]


def get_universe(group: str = "VN30") -> tuple[list[str], str]:
    try:
        from vnstock import Listing
        syms = Listing().symbols_by_group(group)
        syms = sorted({str(s).upper() for s in list(syms) if str(s).isalpha() and len(str(s)) == 3})
        if syms:
            return syms, f"rổ {group} (vnstock)"
    except Exception as e:
        print(f"[!] Không lấy được rổ {group}: {e}")
    return VN30_FALLBACK, "VN30 (danh sách tham khảo)"


def scan(tickers, demo=False, pause=3.5, progress=None):
    """Chấm điểm từng mã. pause = nghỉ giữa các mã để không vượt giới hạn request của API."""
    rows, details, failed = [], {}, []
    for i, t in enumerate(tickers, 1):
        try:
            data = load_data(t, demo=demo)
            a = analyze(data)
            last = a["fin"].iloc[-1]
            rows.append(dict(
                ticker=t, price=a["price"], total=a["total"], quality=a["scores"]["quality"],
                valuation=a["scores"]["valuation"], momentum=a["scores"]["momentum"],
                news=a["scores"].get("news"), rec=a["rec"],
                target=a["target"], upside=a["upside"], pe=a["pe_now"], pb=a["pb_now"],
                roe=last.get("roe"), rev_g=a["rev_g"], np_g=a["np_g"], rs6=a["rs6"], ret_3m=a["ret_3m"],
            ))
            details[t] = (data, a)
            msg = f"[{i}/{len(tickers)}] {t}: {a['total']:.0f} điểm – {a['rec']}"
        except Exception as e:
            failed.append((t, str(e)[:80]))
            msg = f"[{i}/{len(tickers)}] {t}: LỖI {str(e)[:80]}"
        print(msg)
        if progress:
            progress(i / len(tickers), msg)
        live = t in details and "ảnh chụp" not in details[t][0].get("price_source", "")
        if not demo and live and i < len(tickers):
            time.sleep(pause)  # chỉ nghỉ khi gọi API thật, tránh vượt giới hạn request
    df = pd.DataFrame(rows)
    if len(df):
        df = df.sort_values("total", ascending=False).reset_index(drop=True)
        df.index = df.index + 1
    return df, details, failed


# ---------------------------------------------------------------------
# PDF tổng hợp thị trường
# ---------------------------------------------------------------------

def _chart_top(df, n=15):
    d = df.head(n).iloc[::-1]
    fig, ax = plt.subplots(figsize=(9, 0.32 * len(d) + 0.8))
    # đóng góp từng trụ vào điểm tổng (cùng trọng số với analyzer.WEIGHTS)
    from analyzer import WEIGHTS
    parts = [("quality", "Chất lượng", "#0e2a52"), ("valuation", "Định giá", "#e08a00"),
             ("momentum", "Động lượng", "#2a9d8f"), ("news", "Tin tức", "#8a6fb0")]
    has_news = d["news"].notna().all() if "news" in d else False
    wsum = sum(WEIGHTS[k] for k, *_ in parts if k != "news" or has_news)
    left = pd.Series(0.0, index=d.index)
    for k, lbl, col in parts:
        if k == "news" and not has_news:
            continue
        val = d[k] * WEIGHTS[k] / wsum
        ax.barh(d["ticker"], val, left=left, color=col, label=lbl)
        left = left + val
    ax.axvline(70, color="#108040", ls="--", lw=1)
    ax.axvline(50, color="#be1e2d", ls=":", lw=1)
    ax.set_xlim(0, 100)
    ax.set_title(f"Top {len(d)} cổ phiếu theo điểm tổng hợp (đóng góp từng trụ cột)", fontsize=10, loc="left")
    ax.legend(fontsize=7, frameon=False, loc="lower right", ncol=4)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    return _png(fig)


def _chart_map(df):
    fig, ax = plt.subplots(figsize=(9, 3.6))
    import numpy as np  # rung nhẹ điểm để nhãn không chồng nhau (điểm số rời rạc)
    rng = np.random.default_rng(0)
    df = df.assign(valuation=df["valuation"] + rng.uniform(-2.5, 2.5, len(df)),
                   quality=df["quality"] + rng.uniform(-2.5, 2.5, len(df)))
    colors = df["rec"].map({"MUA": "#108040", "THEO DÕI / NẮM GIỮ": "#c88c00"}).fillna("#be1e2d")
    ax.scatter(df["valuation"], df["quality"], s=40 + df["momentum"] * 2, c=colors, alpha=.75, edgecolor="white")
    for _, r in df.iterrows():
        ax.annotate(r["ticker"], (r["valuation"], r["quality"]), fontsize=6.5, xytext=(3, 3), textcoords="offset points")
    ax.axhline(50, color="#999", lw=.8, ls=":")
    ax.axvline(50, color="#999", lw=.8, ls=":")
    ax.set_xlabel("Điểm định giá (càng cao càng rẻ)", fontsize=8)
    ax.set_ylabel("Điểm chất lượng", fontsize=8)
    ax.set_title("Bản đồ cơ hội: Chất lượng × Định giá (kích thước = động lượng)", fontsize=10, loc="left")
    ax.text(97, 97, "Tốt & rẻ", ha="right", va="top", fontsize=8, color="#108040")
    ax.set_xlim(-3, 103); ax.set_ylim(-3, 103)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    return _png(fig)


def build_market_pdf(df, failed, universe_name, demo, out_path, source, market_news=None):
    meta = dict(source=source, last_session=dt.date.today().strftime("%d/%m/%Y"),
                fetched_at=dt.datetime.now().strftime("%H:%M %d/%m/%Y"))
    pdf = Report(meta)
    pdf.alias_nb_pages()
    pdf.add_page()
    if demo:
        pdf.set_font("VN", "B", 9)
        pdf.set_text_color(190, 30, 45)
        pdf.multi_cell(0, 5, "CHẾ ĐỘ KIỂM THỬ: BCTC là số liệu thật, GIÁ và TIN TỨC là MÔ PHỎNG.",
                       new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("VN", "B", 18)
    pdf.set_text_color(*NAVY)
    pdf.cell(0, 10, "BÁO CÁO SÀNG LỌC CƠ HỘI ĐẦU TƯ", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("VN", "", 9.5)
    pdf.set_text_color(*GREY)
    pdf.cell(0, 5, f"Phạm vi: {universe_name}  •  Phân tích thành công {len(df)} mã"
                   + (f", lỗi {len(failed)} mã" if failed else ""), new_x="LMARGIN", new_y="NEXT")
    pdf.set_text_color(0, 0, 0)
    pdf.ln(3)

    # Ô tổng quan
    counts = df["rec"].value_counts()
    boxes = [("MUA", counts.get("MUA", 0), (16, 128, 64)),
             ("THEO DÕI / NẮM GIỮ", counts.get("THEO DÕI / NẮM GIỮ", 0), (200, 140, 0)),
             ("TRÁNH / BÁN", counts.get("TRÁNH / BÁN", 0), (190, 30, 45)),
             ("Điểm TB thị trường", f"{df['total'].mean():.0f}", NAVY)]
    y0, x = pdf.get_y(), 14
    for lbl, val, col in boxes:
        pdf.set_fill_color(*col)
        pdf.rect(x, y0, 44, 20, "F")
        pdf.set_xy(x, y0 + 3)
        pdf.set_text_color(255, 255, 255)
        pdf.set_font("VN", "B", 14)
        pdf.cell(44, 8, str(val), align="C", new_x="LEFT", new_y="NEXT")
        pdf.set_font("VN", "", 7.5)
        pdf.cell(44, 5, lbl, align="C")
        x += 46
    pdf.set_text_color(0, 0, 0)
    pdf.set_y(y0 + 24)

    pdf.h2("Nhận định tự động")
    pdf.set_font("VN", "", 9)
    top = df.head(5)
    best_q = df.sort_values("quality", ascending=False).iloc[0]
    best_v = df.sort_values("valuation", ascending=False).iloc[0]
    best_m = df.sort_values("momentum", ascending=False).iloc[0]
    sweet = df[(df["quality"] >= 60) & (df["valuation"] >= 60)]
    notes = [
        f"Top 5 điểm tổng hợp: {', '.join(f'{r.ticker} ({r.total:.0f})' for r in top.itertuples())}.",
        f"Chất lượng cao nhất: {best_q.ticker} ({best_q.quality:.0f}); định giá hấp dẫn nhất: "
        f"{best_v.ticker} ({best_v.valuation:.0f}); động lượng mạnh nhất: {best_m.ticker} ({best_m.momentum:.0f}).",
        ("Nhóm 'tốt & rẻ' (chất lượng ≥ 60 và định giá ≥ 60): " + ", ".join(sweet["ticker"]) + ".")
        if len(sweet) else "Chưa có mã nào vừa chất lượng ≥ 60 vừa định giá ≥ 60.",
        f"{(df['momentum'] >= 50).mean() * 100:.0f}% số mã có điểm động lượng ≥ 50, "
        f"phản ánh độ rộng xu hướng tăng của nhóm được quét.",
    ]
    for n_ in notes:
        pdf.multi_cell(0, 5, "•  " + n_, new_x="LMARGIN", new_y="NEXT")
        pdf.ln(0.5)

    market_section(pdf, market_news, limit=6)

    pdf.add_page()
    pdf.h2("Xếp hạng")
    pdf.image(_chart_top(df), x=14, w=182)

    pdf.add_page()
    pdf.h2("Bản đồ cơ hội")
    pdf.image(_chart_map(df), x=14, w=182)

    pdf.h2("Bảng xếp hạng đầy đủ")
    cols = [("#", 8), ("Mã", 13), ("Giá", 20), ("Điểm", 13), ("CL", 12), ("ĐG", 12), ("ĐL", 12),
            ("Khuyến nghị", 32), ("Dư địa", 17), ("P/E", 13), ("ROE", 15), ("RS 6T", 15)]
    def head():
        pdf.set_font("VN", "B", 7.5)
        pdf.set_fill_color(*NAVY)
        pdf.set_text_color(255, 255, 255)
        for h, w in cols:
            pdf.cell(w, 6, h, align="C", fill=True)
        pdf.ln()
        pdf.set_text_color(0, 0, 0)
    head()
    for i, r in df.iterrows():
        if pdf.get_y() > 272:
            pdf.add_page(); head()
        pdf.set_font("VN", "", 7.5)
        pdf.set_fill_color(*(LIGHT if i % 2 else (255, 255, 255)))
        vals = [str(i), r.ticker, _n(r.price), f"{r.total:.0f}", f"{r.quality:.0f}", f"{r.valuation:.0f}",
                f"{r.momentum:.0f}", r.rec, _n(r.upside, 1, "%"), _n(r.pe, 1), _n(r.roe, 1, "%"), _n(r.rs6, 1)]
        for (h, w), v in zip(cols, vals):
            if h == "Khuyến nghị":
                pdf.set_text_color(*((16, 128, 64) if v == "MUA" else (190, 30, 45) if "TRÁNH" in v else (170, 115, 0)))
            pdf.cell(w, 5.2, v, align="C", fill=True)
            pdf.set_text_color(0, 0, 0)
        pdf.ln()
    pdf.ln(2)
    pdf.set_font("VN", "", 7.5)
    pdf.set_text_color(*GREY)
    pdf.multi_cell(0, 4, "CL = Chất lượng (35%), ĐG = Định giá (30%), ĐL = Động lượng (25%), cộng Tin tức (10%); RS 6T = chênh lệch lợi suất "
                         "6 tháng so với VN-Index (điểm %). Phương pháp chấm điểm chi tiết xem trong báo cáo từng mã."
                   + (f" Mã lỗi dữ liệu: {', '.join(t for t, _ in failed)}." if failed else "")
                   + " Báo cáo tạo tự động cho mục đích học tập, không phải khuyến nghị đầu tư.",
                   new_x="LMARGIN", new_y="NEXT")

    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    pdf.output(out_path)
    return out_path


def run_screen(group="VN30", tickers=None, demo=False, top=0, pause=3.5, progress=None):
    if tickers:
        universe, uname = [t.strip().upper() for t in tickers if t.strip()], "danh sách tự chọn"
    elif demo:
        universe, uname = VN30_FALLBACK, "VN30 (mô phỏng)"
    else:
        universe, uname = get_universe(group)
    df, details, failed = scan(universe, demo=demo, pause=pause, progress=progress)
    if df.empty:
        raise RuntimeError("Không phân tích được mã nào. Kiểm tra kết nối/vnstock hoặc dùng --demo.")
    stamp = f"{dt.date.today():%Y%m%d}"
    source = next(iter(details.values()))[0]["source"]
    market_news = next(iter(details.values()))[0].get("market_news")
    Path("output").mkdir(exist_ok=True)
    df.to_csv(f"output/xep_hang_{stamp}.csv", index_label="hang", encoding="utf-8-sig")
    market_pdf = build_market_pdf(df, failed, uname, demo, f"output/SANG_LOC_THI_TRUONG_{stamp}.pdf", source, market_news)
    detail_pdfs = [build_pdf(*details[t], f"output/{t}_{stamp}.pdf") for t in df["ticker"].head(top)]
    return df, market_pdf, detail_pdfs, failed


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Quét & xếp hạng cổ phiếu")
    p.add_argument("--group", default="VN30")
    p.add_argument("--tickers", default="", help="Danh sách mã, vd FPT,HPG,MWG")
    p.add_argument("--top", type=int, default=5, help="Xuất PDF chi tiết cho N mã điểm cao nhất")
    p.add_argument("--pause", type=float, default=3.5, help="Giây nghỉ giữa các mã (tránh bị chặn API)")
    p.add_argument("--demo", action="store_true")
    a = p.parse_args()
    df, mp, dps, failed = run_screen(a.group, a.tickers.split(",") if a.tickers else None, a.demo, a.top, a.pause)
    print("\n" + df[["ticker", "total", "rec", "upside"]].head(10).to_string())
    print(f"\n[OK] Báo cáo thị trường: {mp}")
    for d in dps:
        print(f"[OK] Chi tiết: {d}")
