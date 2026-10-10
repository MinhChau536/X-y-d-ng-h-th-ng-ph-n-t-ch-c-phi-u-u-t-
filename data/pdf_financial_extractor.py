"""
Trích số liệu BCTC từ file PDF theo MÃ SỐ chuẩn của mẫu biểu VAS
(Thông tư 200/2014/TT-BTC và 202/2014/TT-BTC cho BCTC hợp nhất).

Cách làm:
  1. Đọc lớp chữ của PDF (PDF scan không có lớp chữ thì không trích được – cần OCR).
  2. Chia văn bản theo 3 báo cáo nhờ tiêu đề: Bảng cân đối kế toán / Báo cáo tình hình tài chính,
     Báo cáo kết quả hoạt động kinh doanh, Báo cáo lưu chuyển tiền tệ. Dừng ở phần Thuyết minh.
  3. Trong từng báo cáo, tìm dòng chứa mã số chuẩn VÀ nhãn khớp từ khóa của mã đó
     (vd mã 10 trong KQKD phải có chữ "doanh thu") rồi lấy số tiền đầu tiên sau mã = kỳ này.
  4. Đọc "Đơn vị tính" để quy về VND. Kiểm tra Tổng tài sản = Nợ phải trả + VCSH.
"""
from __future__ import annotations

import io
import re
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from data.financial_mapping import strip_accents

# mã số -> (chỉ tiêu chuẩn, từ khóa bắt buộc trong nhãn (bỏ dấu)).
# Mọi từ khóa trong danh sách đều phải có; "a|b" nghĩa là có a HOẶC b.
VAS_CODES: Dict[str, Dict[str, Tuple[str, List[str]]]] = {
    "is": {
        "10": ("revenue", ["doanh thu thuan"]),
        "11": ("cogs", ["gia von"]),
        "20": ("gross_profit", ["loi nhuan gop"]),
        "21": ("financial_income", ["doanh thu hoat dong tai chinh"]),
        "22": ("financial_expense", ["chi phi tai chinh"]),
        "23": ("interest_expense", ["lai vay"]),
        "25": ("selling_expense", ["ban hang"]),
        "26": ("admin_expense", ["quan ly"]),
        "30": ("operating_profit", ["loi nhuan thuan", "hoat dong kinh doanh"]),
        "50": ("profit_before_tax", ["truoc thue"]),
        "51": ("income_tax", ["thue"]),
        "60": ("net_income", ["sau thue"]),
        "61": ("net_income_parent", ["cong ty me"]),
        "62": ("minority_profit", ["khong kiem soat|thieu so"]),
        "70": ("eps", ["lai co ban"]),
    },
    "bs": {
        "100": ("current_assets", ["ngan han"]),
        "110": ("cash", ["tien"]),
        "120": ("short_term_investments", ["dau tu tai chinh ngan han"]),
        "130": ("receivables", ["phai thu"]),
        "140": ("inventory", ["hang ton kho"]),
        "220": ("fixed_assets", ["tai san co dinh"]),
        "270": ("total_assets", ["tong", "tai san"]),
        "300": ("total_liabilities", ["no phai tra"]),
        "310": ("current_liabilities", ["no ngan han"]),
        "311": ("payables", ["nguoi ban"]),
        "320": ("short_term_debt", ["vay"]),
        "330": ("long_term_liabilities", ["no dai han"]),
        "338": ("long_term_debt", ["vay"]),
        "400": ("equity", ["von chu so huu"]),
        "411": ("charter_capital", ["von gop|von dau tu|von co phan"]),
        "421": ("retained_earnings", ["chua phan phoi"]),
        "429": ("minority_interest", ["khong kiem soat|thieu so"]),
        "440": ("total_liabilities_and_equity", ["tong", "nguon von"]),
    },
    "cf": {
        "02": ("depreciation", ["khau hao"]),
        "20": ("cfo", ["luu chuyen tien thuan", "kinh doanh"]),
        "21": ("capex", ["mua sam"]),
        "30": ("cfi", ["luu chuyen tien thuan", "dau tu"]),
        "36": ("dividends_paid", ["co tuc"]),
        "40": ("cff", ["luu chuyen tien thuan", "tai chinh"]),
    },
}

_HEADINGS = [
    ("bs", ["BANG CAN DOI KE TOAN", "BAO CAO TINH HINH TAI CHINH"]),
    ("is", ["KET QUA HOAT DONG KINH DOANH"]),
    ("cf", ["LUU CHUYEN TIEN TE"]),
    ("notes", ["THUYET MINH BAO CAO TAI CHINH", "BAN THUYET MINH"]),
]
_MONEY_RE = re.compile(
    r"\(?-?\d{1,3}(?:[.,]\d{3})+\)?"          # 1.234.567 hoặc (1.234)
    r"|\(\d{1,3}\)"                             # (720) – số âm nhỏ trong ngoặc
    r"|(?<![\w.,])0(?![\w.,])"                   # 0
    r"|(?<![\w.,])\(?-?\d{4,}\)?(?![\w.,])"     # 1234567 không phân tách
)


def read_pdf_text(data: bytes, max_pages: int = 80) -> List[str]:
    """Văn bản từng trang (cần thư viện pypdf)."""
    from pypdf import PdfReader
    reader = PdfReader(io.BytesIO(data))
    pages = []
    for i, page in enumerate(reader.pages):
        if i >= max_pages:
            break
        try:
            pages.append(page.extract_text() or "")
        except Exception:
            pages.append("")
    return pages


def parse_money(token: str) -> Optional[float]:
    neg = token.startswith("(") and token.endswith(")") or token.startswith("-")
    digits = re.sub(r"[^\d]", "", token)
    if not digits:
        return None
    v = float(digits)
    return -v if neg else v


def detect_unit(text: str) -> float:
    t = strip_accents(text.lower())
    m = re.search(r"don vi(?: tinh)?\s*[:：]?\s*([a-z ]{2,20})", t)
    unit = m.group(1) if m else ""
    if "trieu" in unit:
        return 1e6
    if "nghin" in unit or "ngan" in unit:
        return 1e3
    if "ty" in unit.split()[:1]:
        return 1e9
    return 1.0


def split_statements(pages: List[str]) -> Dict[str, List[str]]:
    sections: Dict[str, List[str]] = {"bs": [], "is": [], "cf": []}
    current: Optional[str] = None
    for page in pages:
        for line in page.splitlines():
            plain = strip_accents(line).upper()
            for key, heads in _HEADINGS:
                if any(h in plain for h in heads) and len(plain) < 120:
                    current = key
                    break
            if current in sections:
                sections[current].append(line)
    return sections


def extract_statement(lines: List[str], statement: str) -> Dict[str, float]:
    codes = VAS_CODES[statement]
    found: Dict[str, float] = {}
    for line in lines:
        money = list(_MONEY_RE.finditer(line))
        if not money:
            continue
        head = line[:money[0].start()]
        label_plain = strip_accents(head.lower())
        for tok in re.finditer(r"(?<![\w.,])(\d{2,3})(?![\w.,])", head):
            code = tok.group(1)
            if code not in codes:
                continue
            key, kws = codes[code]
            if key in found:
                continue
            label_part = label_plain[:tok.start()] + " " + label_plain[tok.end():]
            if all(any(alt in label_part for alt in kw.split("|")) for kw in kws):
                v = parse_money(money[0].group(0))
                if v is not None:
                    found[key] = v
                break
    return found


def extract_financials(data: bytes) -> Dict[str, Any]:
    """
    Trả về {"values": {chỉ tiêu: giá trị VND}, "unit": hệ số, "checks": {...}, "pages": n, "text_found": bool}
    """
    pages = read_pdf_text(data)
    full = "\n".join(pages)
    if len(full.strip()) < 200:
        return {"values": {}, "unit": None, "checks": {}, "pages": len(pages), "text_found": False,
                "note": "PDF không có lớp chữ (có thể là bản scan) – cần OCR để trích số liệu"}
    unit = detect_unit(full)
    sections = split_statements(pages)
    values: Dict[str, float] = {}
    for st in ("is", "bs", "cf"):
        for k, v in extract_statement(sections[st], st).items():
            values[k] = v * (unit if k != "eps" else 1.0)
    checks = {}
    ta, tle = values.get("total_assets"), values.get("total_liabilities_and_equity")
    if ta and values.get("total_liabilities") is not None and values.get("equity") is not None:
        diff = abs(ta - values["total_liabilities"] - values["equity"]) / abs(ta)
        checks["balance_identity"] = diff < 0.01
    if ta and tle:
        checks["assets_equal_sources"] = abs(ta - tle) / abs(ta) < 0.001
    values.pop("total_liabilities_and_equity", None)
    values.pop("minority_profit", None)
    return {"values": values, "unit": unit, "checks": checks, "pages": len(pages), "text_found": True}


def to_wide(records: List[Tuple[int, Dict[str, float]]]) -> pd.DataFrame:
    """[(khóa kỳ, values)] -> bảng rộng canonical."""
    if not records:
        return pd.DataFrame()
    df = pd.DataFrame({k: v for k, v in records}).T
    df.index = df.index.astype(int)
    df.index.name = "period_key"
    return df.sort_index()
