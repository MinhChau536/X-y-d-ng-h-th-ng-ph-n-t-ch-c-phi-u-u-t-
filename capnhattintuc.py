import subprocess, sys

try:
    import feedparser, reportlab  # noqa
except ImportError:
    subprocess.run([sys.executable, "-m", "pip", "install", "-q", "feedparser", "reportlab"], check=False)

import os, re, json, unicodedata
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta, timezone
from difflib import SequenceMatcher
from typing import Optional, List
from urllib.parse import quote

import requests
import feedparser

DAYS      = 30            # số ngày tin gần nhất
MAX_ITEMS = 15            # số tin hiển thị trong PDF mỗi mã
USE_LLM   = False         # True nếu đã đặt ANTHROPIC_API_KEY

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; StockResearchBot/1.0)"}
TIMEOUT = 15

GOOGLE_NEWS = "https://news.google.com/rss/search?q={q}+when:{d}d&hl=vi&gl=VN&ceid=VN:vi"
GENERAL_RSS = {
    "CafeF - Chứng khoán": "https://cafef.vn/thi-truong-chung-khoan.rss",
    "CafeF - Doanh nghiệp": "https://cafef.vn/doanh-nghiep.rss",
    "Vietstock - Cổ phiếu": "https://vietstock.vn/830/chung-khoan/co-phieu.rss",
    "VnExpress - Kinh doanh": "https://vnexpress.net/rss/kinh-doanh.rss",
}
TARGET_QUERIES = ["{t} kết quả kinh doanh", "{t} cổ tức", "{t} khuyến nghị giá mục tiêu",
                  "{n} lợi nhuận quý", "{n} cổ đông"]

POSITIVE = {
    "lợi nhuận tăng": 1.5, "lãi tăng": 1.5, "lãi đậm": 1.5, "tăng trưởng": 1.0,
    "vượt kế hoạch": 1.5, "kỷ lục": 0.8, "bứt phá": 1.2, "đột phá": 1.0,
    "trả cổ tức": 1.0, "chia cổ tức": 1.0, "cổ tức bằng tiền": 1.0,
    "trúng thầu": 1.2, "ký hợp đồng": 0.8, "hợp tác chiến lược": 0.8, "mở rộng": 0.7,
    "khuyến nghị mua": 1.5, "nâng dự phóng": 1.3, "nâng giá mục tiêu": 1.3,
    "hưởng lợi": 1.0, "khả quan": 1.0, "tích cực": 0.8, "mua ròng": 1.0,
    "tăng mạnh": 1.0, "cải thiện": 0.8, "mua lại cổ phiếu": 1.0, "nâng hạng": 1.0,
    "vinh danh": 0.5, "giải thưởng": 0.4, "thương hiệu mạnh": 0.5, "lãi": 0.8,
    "doanh thu tăng": 1.2, "xuất khẩu tăng": 1.0,
}
NEGATIVE = {
    "thua lỗ": 1.8, "lỗ": 1.5, "lợi nhuận giảm": 1.5, "lãi giảm": 1.5, "doanh thu giảm": 1.2,
    "sụt giảm": 1.2, "giảm sâu": 1.3, "giảm mạnh": 1.0, "nợ xấu": 1.3,
    "vi phạm": 1.5, "bị phạt": 1.5, "xử phạt": 1.5, "khởi tố": 2.0, "bắt tạm giam": 2.0,
    "điều tra": 1.5, "thanh tra": 1.0, "bán ròng": 1.0, "hạ dự phóng": 1.3,
    "hạ khuyến nghị": 1.3, "hạ giá mục tiêu": 1.3, "cảnh báo": 1.0, "đình chỉ": 1.8,
    "hủy niêm yết": 2.0, "diện cảnh báo": 1.5, "cắt margin": 1.3, "chậm công bố": 1.2,
    "chậm nộp": 1.2, "rủi ro": 0.7, "áp lực": 0.7, "khó khăn": 0.9, "nợ quá hạn": 1.5,
    "mất thanh khoản": 1.3, "từ nhiệm": 0.6, "trái phiếu quá hạn": 1.8, "ngừng sản xuất": 1.2,
    "thu hồi sản phẩm": 1.5, "kiện": 0.8,
}
NEGATORS = {"không", "chưa", "chẳng", "hết", "tránh", "thoát", "xóa", "xoá"}
NEUTRAL_MASK = ["giảm giá", "khuyến mãi", "siêu sale", "giảm giá sâu", "ưu đãi"]

NOISE_DROP = ["chứng quyền", "mời thầu", "siêu sale", "khuyến mãi", "tuyển dụng", "dân vũ",
              "người cao tuổi", "giảm giá", "học bổng", "xổ số", "horoscope", "bảng giá sữa",
              "mã giảm giá", "voucher"]

EVENT_RULES = {
    "Kết quả kinh doanh": ["kết quả kinh doanh", "lợi nhuận", "doanh thu", "quý", "báo cáo tài chính", "lãi", "lỗ"],
    "Cổ tức & cổ phiếu": ["cổ tức", "phát hành", "chia thưởng", "tăng vốn", "esop", "mua lại cổ phiếu", "chốt quyền", "đại hội cổ đông", "cổ đông"],
    "M&A & đầu tư": ["m&a", "sáp nhập", "thâu tóm", "thoái vốn", "góp vốn", "dự án", "đầu tư", "liên doanh", "nhà máy"],
    "Ban lãnh đạo": ["bổ nhiệm", "miễn nhiệm", "từ nhiệm", "chủ tịch", "tổng giám đốc", "ceo", "hđqt", "giao dịch nội bộ"],
    "Pháp lý & rủi ro": ["khởi tố", "điều tra", "xử phạt", "bị phạt", "thanh tra", "vi phạm", "đình chỉ", "cảnh báo", "hủy niêm yết", "thu hồi"],
    "Nợ & trái phiếu": ["trái phiếu", "nợ vay", "đáo hạn", "nợ xấu", "tín dụng"],
    "Khuyến nghị & phân tích": ["khuyến nghị", "giá mục tiêu", "dự phóng", "công ty chứng khoán", "định giá"],
    "Vĩ mô & ngành": ["ngành", "thị trường", "chính sách", "lãi suất", "tỷ giá", "thuế", "xuất khẩu"],
    "Thương hiệu & truyền thông": ["vinh danh", "giải thưởng", "thương hiệu", "50 năm", "đồng hành", "fortune", "forbes"],
}
EVENT_WEIGHT = {
    "Kết quả kinh doanh": 1.0, "Cổ tức & cổ phiếu": 0.9, "Khuyến nghị & phân tích": 0.9,
    "Pháp lý & rủi ro": 1.0, "Nợ & trái phiếu": 0.8, "M&A & đầu tư": 0.8,
    "Ban lãnh đạo": 0.6, "Vĩ mô & ngành": 0.5, "Thương hiệu & truyền thông": 0.25, "Khác": 0.2,
}

VN_ONLY = re.compile(r"[đĐơƠưƯạảấầẩẫậắằẳẵặẹẻẽếềểễệỉịọỏốồổỗộớờởỡợụủứừửữựỳỵỷỹ]", re.I)

@dataclass
class NewsItem:
    title: str
    url: str
    source: str
    published: Optional[datetime]
    summary: str = ""
    event: str = "Khác"
    sentiment: float = 0.0
    label: str = "Trung lập"
    reason: str = ""
    relevance: float = 1.0

@dataclass
class NewsReport:
    ticker: str
    company: str
    days: int
    generated_at: str
    total_found: int = 0           # số tin sau lọc (trước khi chọn top)
    items: List[NewsItem] = field(default_factory=list)
    score: float = 0.0
    verdict: str = "Trung lập"
    counts: dict = field(default_factory=dict)
    events: dict = field(default_factory=dict)
    key_risks: List[str] = field(default_factory=list)
    key_catalysts: List[str] = field(default_factory=list)
    narrative: str = ""
    pdf_path: str = ""

    def to_dict(self):
        d = asdict(self)
        for it in d["items"]:
            if it["published"]:
                it["published"] = it["published"].isoformat()
        return d

COMPANY_DB = {
    "VNM": ("Vinamilk", ["Sữa Việt Nam"]), "FPT": ("FPT", ["Tập đoàn FPT"]),
    "HPG": ("Hòa Phát", ["Tập đoàn Hòa Phát"]), "VCB": ("Vietcombank", ["Ngân hàng Ngoại thương"]),
    "VIC": ("Vingroup", ["Tập đoàn Vingroup"]), "VHM": ("Vinhomes", []), "VRE": ("Vincom Retail", []),
    "MWG": ("Thế Giới Di Động", ["Thế giới Di động"]), "MSN": ("Masan", ["Tập đoàn Masan"]),
    "TCB": ("Techcombank", []), "ACB": ("ACB", ["Ngân hàng Á Châu"]), "BID": ("BIDV", []),
    "CTG": ("VietinBank", ["Vietinbank"]), "MBB": ("MB Bank", ["MBBank", "Ngân hàng Quân đội"]),
    "VPB": ("VPBank", []), "STB": ("Sacombank", []), "HDB": ("HDBank", []), "TPB": ("TPBank", []),
    "VIB": ("VIB", []), "SHB": ("SHB", []), "SSB": ("SeABank", []), "LPB": ("LPBank", ["LienVietPostBank"]),
    "SSI": ("SSI", ["Chứng khoán SSI"]), "VND": ("VNDirect", []), "VCI": ("Vietcap", []),
    "GAS": ("PV GAS", ["PV Gas", "Khí Việt Nam"]), "PLX": ("Petrolimex", []), "POW": ("PV Power", ["PVPower"]),
    "SAB": ("Sabeco", ["Bia Sài Gòn"]), "VJC": ("Vietjet", ["Vietjet Air"]), "HVN": ("Vietnam Airlines", []),
    "GVR": ("Cao su Việt Nam", ["Tập đoàn Công nghiệp Cao su"]), "PNJ": ("PNJ", ["Vàng bạc Phú Nhuận"]),
    "DGC": ("Đức Giang", ["Hóa chất Đức Giang"]), "DPM": ("Đạm Phú Mỹ", []), "DCM": ("Đạm Cà Mau", []),
    "REE": ("REE", ["Cơ điện lạnh"]), "KDH": ("Khang Điền", []), "NVL": ("Novaland", []),
    "HAG": ("Hoàng Anh Gia Lai", []), "BVH": ("Bảo Việt", []), "VPI": ("Văn Phú Invest", []),
}

def resolve_company(ticker, override=""):
    """Trả về (tên, [tên gọi khác]). Thứ tự: nhập tay -> từ điển -> vnstock (nếu có) -> chỉ dùng mã."""
    t = ticker.upper()
    if override:
        return override, []
    if t in COMPANY_DB:
        name, al = COMPANY_DB[t]
        return name, al
    try:                                    
        from vnstock import Vnstock
        prof = Vnstock().stock(symbol=t, source="VCI").company.profile()
        name = str(prof["company_name"].iloc[0])
        name = re.sub(r"^(Công ty Cổ phần|CTCP|Tổng công ty|Ngân hàng TMCP|Ngân hàng Thương mại Cổ phần)\s+", "", name, flags=re.I)
        return name, []
    except Exception:
        return "", []                       

def _norm(s):
    return unicodedata.normalize("NFC", s or "").lower().strip()

def _clean(s):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", s or "")).strip()

def fetch_feed(url, source):
    try:
        r = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
        r.raise_for_status()
        feed = feedparser.parse(r.content)
    except Exception as e:
        print(f"[CẢNH BÁO] Không đọc được '{source}': {str(e)[:80]}")
        return []
    out = []
    for e in feed.entries:
        pub = None
        if getattr(e, "published_parsed", None):
            pub = datetime(*e.published_parsed[:6], tzinfo=timezone.utc)
        title, src = _clean(getattr(e, "title", "")), source
        if source == "Google News" and " - " in title:
            title, src = title.rsplit(" - ", 1)
        out.append(NewsItem(title, getattr(e, "link", ""), src, pub, _clean(getattr(e, "summary", ""))[:500]))
    return out

def collect(ticker, names, days):
    items = []
    base = [f'"{ticker}" cổ phiếu'] + [f'"{n}"' for n in names[:3]]
    name = names[0] if names else ticker
    targeted = [q.format(t=ticker, n=name) for q in TARGET_QUERIES]
    for q in base + targeted:
        items += fetch_feed(GOOGLE_NEWS.format(q=quote(q), d=days), "Google News")
    for src, url in GENERAL_RSS.items():
        items += fetch_feed(url, src)
    print(f"Đã thu thập {len(items)} tin thô.")
    return items

def is_vietnamese(it):
    return bool(VN_ONLY.search(it.title + " " + it.summary))

def is_noise(it):
    t = _norm(it.title)
    return any(k in t for k in NOISE_DROP)

def filter_relevant(items, ticker, names, days):
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    tk = re.compile(rf"(?<![A-Za-z0-9]){re.escape(ticker)}(?![A-Za-z0-9])", re.I)
    nm = [re.compile(re.escape(_norm(n))) for n in names if n]
    kept, drop = [], {"cũ": 0, "ngoại ngữ": 0, "nhiễu": 0, "không liên quan": 0}
    for it in items:
        if it.published and it.published < cutoff:
            drop["cũ"] += 1; continue
        if not is_vietnamese(it):
            drop["ngoại ngữ"] += 1; continue
        if is_noise(it):
            drop["nhiễu"] += 1; continue
        t_hit = bool(tk.search(it.title)) or any(p.search(_norm(it.title)) for p in nm)
        s_hit = bool(tk.search(it.summary)) or any(p.search(_norm(it.summary)) for p in nm)
        if t_hit:   it.relevance = 1.0
        elif s_hit: it.relevance = 0.6
        else:
            drop["không liên quan"] += 1; continue
        kept.append(it)
    print("Đã loại:", drop)
    return kept

def _tokens(s):
    return set(re.findall(r"\w+", _norm(s)))

def dedupe(items, thr=0.8, jac=0.6):
    epoch = datetime.min.replace(tzinfo=timezone.utc)
    items = sorted(items, key=lambda x: (x.relevance, x.published or epoch), reverse=True)
    uniq = []
    for it in items:
        t, tk = _norm(it.title), _tokens(it.title)
        dup = False
        for u in uniq:
            uk = _tokens(u.title)
            j = len(tk & uk) / max(1, len(tk | uk))
            if SequenceMatcher(None, t, _norm(u.title)).ratio() >= thr or j >= jac:
                dup = True; break
        if not dup:
            uniq.append(it)
    return uniq

def classify_event(text):
    t = _norm(text)
    best, best_n = "Khác", 0
    for ev, kws in EVENT_RULES.items():
        n = sum(1 for k in kws if k in t)
        if n > best_n:
            best, best_n = ev, n
    return best

def lexicon_sentiment(title, summary=""):
    pos = neg = 0.0
    reasons = []
    entries = [(p, w, 1) for p, w in POSITIVE.items()] + [(p, w, -1) for p, w in NEGATIVE.items()]
    entries.sort(key=lambda x: -len(x[0]))
    for text, mult in ((_norm(title), 2.0), (_norm(summary), 1.0)):
        for ph in NEUTRAL_MASK:
            text = text.replace(ph, " " * len(ph))
        for phrase, w, sign in entries:
            for m in list(re.finditer(rf"(?<!\w){re.escape(phrase)}(?!\w)", text)):
                before = text[max(0, m.start() - 20):m.start()].split()[-2:]
                s = -sign if any(b in NEGATORS for b in before) else sign
                if s > 0: pos += w * mult
                else:     neg += w * mult
                reasons.append(("+" if s > 0 else "-") + phrase)
                text = text[:m.start()] + " " * (m.end() - m.start()) + text[m.end():]
    total = pos + neg
    score = 0.0 if total == 0 else (pos - neg) / (total + 2.0)
    return max(-1.0, min(1.0, score)), ", ".join(dict.fromkeys(reasons))

def label_of(s):
    return "Tích cực" if s > 0.15 else "Tiêu cực" if s < -0.15 else "Trung lập"

def llm_refine(items, model="claude-sonnet-4-6"):
    try:
        import anthropic
        client = anthropic.Anthropic()
    except Exception as e:
        print("[INFO] Bỏ qua LLM:", e); return
    payload = [{"id": i, "title": it.title, "summary": it.summary[:300]} for i, it in enumerate(items)]
    prompt = ("Bạn là chuyên viên phân tích chứng khoán. Với mỗi tin, chấm tác động tới giá cổ phiếu "
              "từ -1 đến 1, kèm lý do <=12 từ. Chỉ trả JSON: [{\"id\":0,\"score\":0.3,\"reason\":\"...\"}].\n"
              + json.dumps(payload, ensure_ascii=False))
    try:
        msg = client.messages.create(model=model, max_tokens=4000, messages=[{"role": "user", "content": prompt}])
        txt = re.sub(r"```json|```", "", msg.content[0].text).strip()
        for r in json.loads(txt):
            it = items[r["id"]]
            it.sentiment = round(0.6 * float(r["score"]) + 0.4 * it.sentiment, 3)
            it.reason = r.get("reason", it.reason)
    except Exception as e:
        print("[CẢNH BÁO] LLM lỗi, giữ kết quả từ điển:", e)

def priority(it, now):
    age = (now - it.published).days if it.published else 14
    return EVENT_WEIGHT.get(it.event, 0.2) * 2 + it.relevance + 0.5 ** (age / 14)

def select_top(items, n):
    now = datetime.now(timezone.utc)
    top = sorted(items, key=lambda x: priority(x, now), reverse=True)[:n]
    epoch = datetime.min.replace(tzinfo=timezone.utc)
    return sorted(top, key=lambda x: x.published or epoch, reverse=True)

def aggregate(items, half_life=14.0):
    now = datetime.now(timezone.utc)
    num = den = 0.0
    for it in items:
        age = (now - it.published).days if it.published else half_life
        w = it.relevance * EVENT_WEIGHT.get(it.event, 0.2) * 0.5 ** (age / half_life)
        num += w * it.sentiment
        den += w
    return num / den if den else 0.0

def narrative_of(rep):
    n = len(rep.items)
    if n == 0:
        return (f"Trong {rep.days} ngày gần đây hệ thống không ghi nhận tin tức đáng kể nào về {rep.ticker}. "
                "Thiếu tin không đồng nghĩa rủi ro thấp; nên đối chiếu công bố thông tin trên HOSE/HNX.")
    c = rep.counts
    s = (f"Trong {rep.days} ngày qua, hệ thống lọc được {rep.total_found} tin liên quan đến "
         f"{rep.company or rep.ticker} ({rep.ticker}); báo cáo trình bày {n} tin có giá trị đầu tư cao nhất: "
         f"{c.get('Tích cực', 0)} tích cực, {c.get('Trung lập', 0)} trung lập, {c.get('Tiêu cực', 0)} tiêu cực. ")
    invest = {k: v for k, v in rep.events.items() if EVENT_WEIGHT.get(k, 0) >= 0.5}
    if invest:
        s += "Nhóm sự kiện chính: " + ", ".join(f'"{k}" ({v})' for k, v in sorted(invest.items(), key=lambda kv: -kv[1])[:3]) + ". "
    else:
        s += "Chưa có sự kiện tác động trực tiếp tới định giá (kết quả kinh doanh, cổ tức, pháp lý); tin chủ yếu mang tính truyền thông thương hiệu. "
    s += f"Điểm tin tức tổng hợp {rep.score:+.2f} → xu hướng {rep.verdict.lower()}."
    if rep.key_catalysts: s += " Yếu tố hỗ trợ: " + "; ".join(rep.key_catalysts[:2]) + "."
    if rep.key_risks:     s += " Rủi ro cần theo dõi: " + "; ".join(rep.key_risks[:2]) + "."
    return s + " Điểm cảm xúc dựa trên phân tích từ khoá nên chỉ mang tính tham khảo."

def build_news_report(ticker, company="", days=30, aliases=None, use_llm=False, max_items=15):
    ticker = ticker.upper().strip()
    names = [n for n in [company] + (aliases or []) if n]
    items = dedupe(filter_relevant(collect(ticker, names, days), ticker, names, days))
    print(f"Còn {len(items)} tin sau khi lọc và khử trùng lặp.")

    for it in items:
        it.event = classify_event(it.title + " " + it.summary)
        it.sentiment, it.reason = lexicon_sentiment(it.title, it.summary)
    if use_llm and items:
        llm_refine(items[:40])
    for it in items:
        it.label = label_of(it.sentiment)

    shown = select_top(items, max_items)
    score = aggregate(shown)
    rep = NewsReport(ticker, company, days, datetime.now().strftime("%d/%m/%Y %H:%M"),
                     total_found=len(items), items=shown, score=round(score, 3), verdict=label_of(score))
    for it in shown:                      # thống kê trên đúng các tin được hiển thị
        rep.counts[it.label] = rep.counts.get(it.label, 0) + 1
        rep.events[it.event] = rep.events.get(it.event, 0) + 1
    ranked = [i for i in shown if EVENT_WEIGHT.get(i.event, 0) >= 0.5]
    rep.key_catalysts = [i.title for i in sorted(ranked, key=lambda x: -x.sentiment)[:3] if i.sentiment > 0.15]
    rep.key_risks = [i.title for i in sorted(ranked, key=lambda x: x.sentiment)[:3] if i.sentiment < -0.15]
    rep.narrative = narrative_of(rep)
    return rep

FONT_CANDIDATES = [
    ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
    ("DejaVuSans.ttf", "DejaVuSans-Bold.ttf"),
]

def register_fonts():
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    for attempt in range(2):
        for reg, bold in FONT_CANDIDATES:
            if os.path.exists(reg) and os.path.exists(bold):
                pdfmetrics.registerFont(TTFont("VN", reg))
                pdfmetrics.registerFont(TTFont("VN-B", bold))
                return
        if attempt == 0:
            subprocess.run(["apt-get", "install", "-y", "-qq", "fonts-dejavu-core"], check=False)
    raise RuntimeError("Không tìm thấy font DejaVu (DejaVuSans.ttf, DejaVuSans-Bold.ttf).")

def news_flowables(rep):
    from reportlab.lib import colors
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.platypus import Paragraph, Spacer, Table, TableStyle
    from reportlab.graphics.shapes import Drawing, Rect, String
    from xml.sax.saxutils import escape

    h  = ParagraphStyle("h",  fontName="VN-B", fontSize=14, spaceAfter=6)
    h2 = ParagraphStyle("h2", fontName="VN-B", fontSize=10.5, spaceBefore=8, spaceAfter=4)
    p  = ParagraphStyle("p",  fontName="VN", fontSize=9.5, leading=14)
    sm = ParagraphStyle("sm", fontName="VN", fontSize=8, leading=10.5)
    col = {"Tích cực": colors.HexColor("#1B7F3B"), "Tiêu cực": colors.HexColor("#C0392B"), "Trung lập": colors.HexColor("#6B7280")}
    grid = TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#F3F4F6")),
                       ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#D1D5DB")),
                       ("VALIGN", (0, 0), (-1, -1), "TOP")])

    fl = [Paragraph(f"Thông tin &amp; tin tức doanh nghiệp - {escape(rep.ticker)}", h),
          Paragraph(f"Cập nhật: {rep.generated_at}", sm), Spacer(1, 4),
          Paragraph(escape(rep.narrative), p), Spacer(1, 8)]

    d = Drawing(440, 32)
    d.add(Rect(0, 14, 440, 10, fillColor=colors.HexColor("#E5E7EB"), strokeColor=None))
    x = 220 + rep.score * 220
    d.add(Rect(min(220, x), 14, abs(x - 220), 10, fillColor=col[rep.verdict], strokeColor=None))
    d.add(Rect(219, 12, 2, 14, fillColor=colors.black, strokeColor=None))
    d.add(String(0, 2, "-1 Tiêu cực", fontName="VN", fontSize=7))
    d.add(String(385, 2, "+1 Tích cực", fontName="VN", fontSize=7))
    fl.append(d)

    if rep.events:
        fl.append(Paragraph("Phân bổ theo loại sự kiện", h2))
        rows = [[Paragraph("<b>Sự kiện</b>", sm), Paragraph("<b>Số tin</b>", sm)]]
        for ev, n in sorted(rep.events.items(), key=lambda kv: -kv[1]):
            rows.append([Paragraph(escape(ev), sm), Paragraph(str(n), sm)])
        t = Table(rows, colWidths=[8 * cm, 2.5 * cm]); t.setStyle(grid); fl.append(t)

    fl.append(Paragraph("Tin tức chi tiết", h2))
    rows = [[Paragraph(f"<b>{x}</b>", sm) for x in ("Ngày", "Tiêu đề", "Nguồn", "Sự kiện", "Cảm xúc")]]
    for it in rep.items:
        dt = it.published.strftime("%d/%m") if it.published else "-"
        rows.append([Paragraph(dt, sm), Paragraph(escape(it.title), sm), Paragraph(escape(it.source), sm),
                     Paragraph(escape(it.event), sm),
                     Paragraph(f'<font color="#{col[it.label].hexval()[2:]}">{it.label} ({it.sentiment:+.2f})</font>', sm)])
    t = Table(rows, colWidths=[1.3 * cm, 8 * cm, 2.5 * cm, 2.8 * cm, 2.4 * cm], repeatRows=1)
    t.setStyle(grid)
    fl += [t, Spacer(1, 4),
           Paragraph("Nguồn: Google News, CafeF, Vietstock, VnExpress. Đã loại tin trùng lặp, tin ngoại ngữ và tin quảng cáo. "
                     "Cảm xúc chấm tự động, chỉ mang tính tham khảo.", sm)]
    return fl

def export_pdf(rep, path):
    from reportlab.platypus import SimpleDocTemplate
    from reportlab.lib.pagesizes import A4
    register_fonts()
    SimpleDocTemplate(path, pagesize=A4, leftMargin=36, rightMargin=36, topMargin=36, bottomMargin=36).build(news_flowables(rep))
    return path

def analyze(ticker, company="", days=DAYS, max_items=MAX_ITEMS, use_llm=USE_LLM, make_pdf=True):
    """Hàm chính để tích hợp vào hệ thống: nhận mã cổ phiếu bất kỳ -> NewsReport (+ PDF)."""
    ticker = ticker.upper().strip()
    if not re.fullmatch(r"[A-Z0-9]{2,5}", ticker):
        raise ValueError(f"Mã cổ phiếu không hợp lệ: {ticker!r}")
    name, aliases = resolve_company(ticker, company)
    print(f"\n===== {ticker} | {name or '(chưa rõ tên doanh nghiệp, lọc theo mã)'} =====")
    rep = build_news_report(ticker, name, days, aliases, use_llm, max_items)
    if make_pdf:
        rep.pdf_path = export_pdf(rep, f"tin_tuc_{ticker}.pdf")
    return rep

def run_cli():
    raw = input("Nhập mã cổ phiếu (nhiều mã cách nhau dấu phẩy, ví dụ: VNM, FPT, HPG): ").strip()
    tickers = [t.strip().upper() for t in re.split(r"[,\s;]+", raw) if t.strip()] or ["VNM"]
    results = []
    for t in tickers:
        try:
            rep = analyze(t)
        except Exception as e:
            print(f"[LỖI] {t}: {e}"); continue
        print("\n" + rep.narrative + "\n")
        for it in rep.items:
            d = it.published.strftime("%d/%m/%Y") if it.published else "--"
            print(f"[{d}] {it.label:9s} {it.sentiment:+.2f} | {it.event:26s} | {it.title} ({it.source})")
        results.append(rep)
    if len(results) > 1:                                    
        print("\n===== SO SÁNH =====")
        print(f"{'Mã':6s}{'Điểm':>8s}  {'Xu hướng':10s}{'Số tin':>7s}")
        for r in sorted(results, key=lambda r: -r.score):
            print(f"{r.ticker:6s}{r.score:>+8.2f}  {r.verdict:10s}{r.total_found:>7d}")
    try:
        from google.colab import files
        for r in results:
            files.download(r.pdf_path)
    except Exception:
        pass
    return results

if __name__ == "__main__":      
    results = run_cli()
