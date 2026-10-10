"""
Chuẩn hóa BCTC từ mọi nguồn về MỘT bộ chỉ tiêu chuẩn (canonical items).

Đầu vào chấp nhận:
  (a) Dạng ma trận  : cột item / item_en / item_id + mỗi cột là một kỳ (vnstock v4 VCI/KBS, Vietstock)
  (b) Dạng bảng     : mỗi dòng là một kỳ, có cột Năm / Kỳ, mỗi cột là một chỉ tiêu (vnstock v3)
Đầu ra: DataFrame "rộng" – index = khóa kỳ (năm*10 + quý, tăng dần), cột = chỉ tiêu chuẩn,
giá trị quy về VND (trừ EPS/BVPS tính bằng đồng/cp và số cổ phiếu).

Quy tắc khớp cho từng chỉ tiêu, theo thứ tự ưu tiên:
  1. item_id trùng khớp chính xác (KBS đã chuẩn hóa: revenue, net_profit, total_assets…)
  2. Tên tiếng Việt BẮT ĐẦU bằng mẫu (sau khi bỏ số thứ tự "I.", "1.", "A."…)
  3. Tên tiếng Việt CHỨA mẫu
  4. Tương tự với tên tiếng Anh
Mọi bước đều loại các dòng chứa từ loại trừ (vd "tăng trưởng", "%", "biên") để tránh
lấy nhầm dòng "Tăng trưởng doanh thu (%)" thay cho "Doanh thu".
So khớp cả bản có dấu và bản bỏ dấu tiếng Việt.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from analytics.period_utils import (
    META_COLS, _norm, flatten_columns, key_to_label, order_tabular, parse_period_key,
)


def strip_accents(text: str) -> str:
    text = unicodedata.normalize("NFD", str(text))
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    return text.replace("đ", "d").replace("Đ", "D")


_ENUM_RE = re.compile(r"^\s*(?:[-–•+]\s*)?(?:(?:[ivxlcdm]+|[a-z]|\d+(?:\.\d+)*)\s*[\.\)\-–:/]\s*)?", re.I)


def norm_label(text) -> str:
    """Chuẩn hóa nhãn: chữ thường, bỏ số thứ tự đầu dòng, gộp khoảng trắng."""
    if text is None or (isinstance(text, float) and np.isnan(text)):
        return ""
    t = unicodedata.normalize("NFC", str(text)).lower().strip()
    t = _ENUM_RE.sub("", t, count=1)
    t = re.sub(r"\s+", " ", t)
    return t.strip()


@dataclass
class Item:
    key: str
    statement: str            # is | bs | cf | ratio
    label_vi: str
    ids: List[str] = field(default_factory=list)
    vi: List[str] = field(default_factory=list)
    en: List[str] = field(default_factory=list)
    exclude: List[str] = field(default_factory=list)
    unit: str = "vnd"         # vnd | per_share | shares | ratio


_COMMON_EXCL = ["tăng trưởng", "growth", "%", "yoy", "qoq", "biên", "margin", "vòng quay", "turnover",
                "/", "trên ", " per ", "tỷ lệ", "ratio", "tỷ suất"]

CANONICAL_ITEMS: List[Item] = [
    # ── Kết quả kinh doanh ──
    Item("revenue", "is", "Doanh thu thuần",
         ids=["revenue", "net_revenue", "net_sales", "doanh_thu_thuan", "operating_income_revenue"],
         vi=["doanh thu thuần về bán hàng", "doanh thu thuần", "doanh số thuần", "doanh thu"],
         en=["net revenue", "net sales", "revenue"],
         exclude=_COMMON_EXCL + ["giảm trừ", "deduction", "tài chính", "financial", "khác", "other",
                                 "chưa thực hiện", "unearned", "nhận trước"]),
    Item("cogs", "is", "Giá vốn hàng bán", ids=["cost_of_goods_sold", "cogs"],
         vi=["giá vốn hàng bán", "giá vốn"], en=["cost of goods sold", "cost of sales"],
         exclude=_COMMON_EXCL),
    Item("gross_profit", "is", "Lợi nhuận gộp", ids=["gross_profit"],
         vi=["lợi nhuận gộp"], en=["gross profit"], exclude=_COMMON_EXCL),
    Item("financial_income", "is", "Doanh thu hoạt động tài chính", ids=["financial_income"],
         vi=["doanh thu hoạt động tài chính"], en=["financial income"], exclude=_COMMON_EXCL),
    Item("financial_expense", "is", "Chi phí tài chính", ids=["finance_expenses", "financial_expenses"],
         vi=["chi phí tài chính"], en=["financial expense", "finance expense"], exclude=_COMMON_EXCL + ["lãi vay"]),
    Item("interest_expense", "is", "Chi phí lãi vay", ids=["interest_expense", "interest_expenses"],
         vi=["trong đó: chi phí lãi vay", "chi phí lãi vay"], en=["interest expense"], exclude=_COMMON_EXCL),
    Item("selling_expense", "is", "Chi phí bán hàng", ids=["selling_expenses"],
         vi=["chi phí bán hàng"], en=["selling expense"], exclude=_COMMON_EXCL),
    Item("admin_expense", "is", "Chi phí quản lý doanh nghiệp", ids=["admin_expenses", "general_and_administrative_expenses"],
         vi=["chi phí quản lý doanh nghiệp", "chi phí quản lý"], en=["general and administrative", "administrative expense"],
         exclude=_COMMON_EXCL),
    Item("operating_profit", "is", "Lợi nhuận thuần từ HĐKD", ids=["operating_profit"],
         vi=["lợi nhuận thuần từ hoạt động kinh doanh", "lợi nhuận từ hoạt động kinh doanh", "lãi/(lỗ) từ hoạt động kinh doanh"],
         en=["operating profit", "profit from operating activities"], exclude=_COMMON_EXCL + ["trước thuế", "before tax"]),
    Item("profit_before_tax", "is", "Lợi nhuận trước thuế", ids=["profit_before_tax"],
         vi=["tổng lợi nhuận kế toán trước thuế", "lợi nhuận trước thuế", "lãi trước thuế"],
         en=["profit before tax", "accounting profit before tax", "earnings before tax"], exclude=_COMMON_EXCL),
    Item("income_tax", "is", "Chi phí thuế TNDN", ids=["income_tax", "corporate_income_tax"],
         vi=["chi phí thuế thu nhập doanh nghiệp", "chi phí thuế tndn hiện hành", "thuế thu nhập doanh nghiệp"],
         en=["income tax expense", "corporate income tax"], exclude=_COMMON_EXCL + ["hoãn lại", "deferred"]),
    Item("net_income", "is", "Lợi nhuận sau thuế", ids=["net_profit", "net_profit_after_tax", "profit_after_tax"],
         vi=["lợi nhuận sau thuế thu nhập doanh nghiệp", "lợi nhuận sau thuế", "lãi sau thuế"],
         en=["net profit after tax", "profit after tax", "net profit", "net income"],
         exclude=_COMMON_EXCL + ["công ty mẹ", "parent", "thiểu số", "minority", "không kiểm soát",
                                 "non-controlling", "chưa phân phối", "undistributed"]),
    Item("net_income_parent", "is", "LNST của cổ đông công ty mẹ",
         ids=["net_profit_parent", "profit_attributable_to_parent", "net_profit_attributable_to_parent"],
         vi=["lợi nhuận sau thuế của cổ đông công ty mẹ", "cổ đông của công ty mẹ", "cổ đông công ty mẹ"],
         en=["attributable to parent", "attributable to owners of the parent", "parent company"],
         exclude=_COMMON_EXCL),
    Item("eps", "is", "EPS cơ bản (đồng/cp)", ids=["eps", "basic_eps", "earnings_per_share"],
         vi=["lãi cơ bản trên cổ phiếu", "lãi cơ bản trên mỗi cổ phiếu", "eps"],
         en=["basic earnings per share", "earnings per share", "eps"],
         exclude=["pha loãng", "diluted", "tăng trưởng", "growth", "%"], unit="per_share"),
    # Ngân hàng
    Item("net_interest_income", "is", "Thu nhập lãi thuần", ids=["net_interest_income"],
         vi=["thu nhập lãi thuần"], en=["net interest income"], exclude=_COMMON_EXCL),
    Item("total_operating_income", "is", "Tổng thu nhập hoạt động", ids=["total_operating_income"],
         vi=["tổng thu nhập hoạt động"], en=["total operating income"], exclude=_COMMON_EXCL),
    Item("provision_expense", "is", "Chi phí dự phòng rủi ro tín dụng", ids=["provision_for_credit_losses"],
         vi=["chi phí dự phòng rủi ro tín dụng"], en=["provision for credit losses", "credit loss expense"],
         exclude=_COMMON_EXCL),

    # ── Cân đối kế toán ──
    Item("cash", "bs", "Tiền và tương đương tiền", ids=["cash_and_cash_equivalents", "cash"],
         vi=["tiền và các khoản tương đương tiền", "tiền và tương đương tiền"], en=["cash and cash equivalents"],
         exclude=_COMMON_EXCL + ["đầu kỳ", "cuối kỳ", "beginning", "end of", "tăng", "giảm", "increase",
                                 "lưu chuyển", "ảnh hưởng"]),
    Item("short_term_investments", "bs", "Đầu tư tài chính ngắn hạn", ids=["short_term_investments"],
         vi=["đầu tư tài chính ngắn hạn", "các khoản đầu tư tài chính ngắn hạn"],
         en=["short-term investments", "short term financial investments", "short-term financial investments"],
         exclude=_COMMON_EXCL),
    Item("receivables", "bs", "Phải thu ngắn hạn", ids=["short_term_receivables", "accounts_receivable"],
         vi=["các khoản phải thu ngắn hạn", "phải thu ngắn hạn"], en=["short-term receivables", "accounts receivable"],
         exclude=_COMMON_EXCL + ["khác", "other", "dự phòng", "provision", "nội bộ"]),
    Item("inventory", "bs", "Hàng tồn kho", ids=["inventories", "inventory"],
         vi=["hàng tồn kho"], en=["inventories", "inventory"],
         exclude=_COMMON_EXCL + ["dự phòng", "provision", "giảm giá", "tăng", "giảm"]),
    Item("current_assets", "bs", "Tài sản ngắn hạn", ids=["current_assets", "short_term_assets"],
         vi=["tài sản ngắn hạn"], en=["current assets", "short-term assets"],
         exclude=_COMMON_EXCL + ["khác", "other", "dài hạn"]),
    Item("fixed_assets", "bs", "Tài sản cố định", ids=["fixed_assets"],
         vi=["tài sản cố định"], en=["fixed assets"],
         exclude=_COMMON_EXCL + ["khấu hao", "depreciation", "mua sắm", "purchase", "thanh lý", "disposal",
                                 "vô hình", "intangible", "thuê tài chính", "xây dựng"]),
    Item("total_assets", "bs", "Tổng tài sản", ids=["total_assets", "assets"],
         vi=["tổng cộng tài sản", "tổng tài sản"], en=["total assets"],
         exclude=_COMMON_EXCL + ["lợi nhuận", "return", "roa"]),
    Item("current_liabilities", "bs", "Nợ ngắn hạn", ids=["current_liabilities", "short_term_liabilities"],
         vi=["nợ ngắn hạn"], en=["current liabilities", "short-term liabilities"],
         exclude=_COMMON_EXCL + ["vay", "borrow", "khác", "other"]),
    Item("long_term_liabilities", "bs", "Nợ dài hạn", ids=["long_term_liabilities", "non_current_liabilities"],
         vi=["nợ dài hạn"], en=["long-term liabilities", "non-current liabilities"],
         exclude=_COMMON_EXCL + ["vay", "borrow", "khác", "other"]),
    Item("payables", "bs", "Phải trả người bán ngắn hạn", ids=["accounts_payable", "short_term_trade_payables"],
         vi=["phải trả người bán ngắn hạn", "phải trả người bán"], en=["short-term trade payables", "accounts payable", "trade payables"],
         exclude=_COMMON_EXCL + ["dài hạn", "long-term", "trả trước", "advance"]),
    Item("short_term_debt", "bs", "Vay ngắn hạn", ids=["short_term_borrowings", "short_term_debt"],
         vi=["vay và nợ thuê tài chính ngắn hạn", "vay và nợ ngắn hạn", "vay ngắn hạn"],
         en=["short-term borrowings", "short-term debt", "short-term loans"], exclude=_COMMON_EXCL),
    Item("long_term_debt", "bs", "Vay dài hạn", ids=["long_term_borrowings", "long_term_debt"],
         vi=["vay và nợ thuê tài chính dài hạn", "vay và nợ dài hạn", "vay dài hạn"],
         en=["long-term borrowings", "long-term debt", "long-term loans"], exclude=_COMMON_EXCL),
    Item("total_liabilities", "bs", "Nợ phải trả", ids=["total_liabilities", "liabilities"],
         vi=["tổng nợ phải trả", "nợ phải trả"], en=["total liabilities", "liabilities"],
         exclude=_COMMON_EXCL + ["ngắn hạn", "dài hạn", "short", "long", "khác", "other", "vốn chủ",
                                 "equity", "người bán", "supplier", "nguồn vốn"]),
    Item("equity", "bs", "Vốn chủ sở hữu", ids=["equity", "owners_equity", "total_equity"],
         vi=["vốn chủ sở hữu"], en=["owner's equity", "owners' equity", "total equity", "equity"],
         exclude=_COMMON_EXCL + ["nợ phải trả và", "liabilities and", "nguồn vốn", "roe", "lợi nhuận",
                                 "return", "khác", "other", "vốn góp", "contributed", "thay đổi", "change"]),
    Item("minority_interest", "bs", "Lợi ích cổ đông không kiểm soát", ids=["minority_interest", "non_controlling_interest"],
         vi=["lợi ích cổ đông không kiểm soát", "lợi ích của cổ đông thiểu số", "cổ đông thiểu số"],
         en=["non-controlling interest", "minority interest"], exclude=_COMMON_EXCL),
    Item("charter_capital", "bs", "Vốn góp của chủ sở hữu", ids=["charter_capital", "share_capital", "paid_in_capital"],
         vi=["vốn góp của chủ sở hữu", "vốn đầu tư của chủ sở hữu", "vốn điều lệ", "vốn cổ phần"],
         en=["paid-in capital", "share capital", "charter capital", "owner's capital"], exclude=_COMMON_EXCL),
    Item("retained_earnings", "bs", "LNST chưa phân phối", ids=["retained_earnings", "undistributed_earnings_after_tax"],
         vi=["lợi nhuận sau thuế chưa phân phối", "lợi nhuận chưa phân phối"], en=["undistributed", "retained earnings"],
         exclude=_COMMON_EXCL),
    Item("customer_loans", "bs", "Cho vay khách hàng", ids=["loans_to_customers"],
         vi=["cho vay khách hàng"], en=["loans to customers"], exclude=_COMMON_EXCL + ["dự phòng", "provision"]),
    Item("customer_deposits", "bs", "Tiền gửi của khách hàng", ids=["deposits_from_customers", "customer_deposits"],
         vi=["tiền gửi của khách hàng"], en=["deposits from customers", "customer deposits"], exclude=_COMMON_EXCL),

    # ── Lưu chuyển tiền tệ ──
    Item("depreciation", "cf", "Khấu hao TSCĐ", ids=["depreciation", "depreciation_and_amortization"],
         vi=["khấu hao tài sản cố định", "khấu hao tscđ", "khấu hao"], en=["depreciation"],
         exclude=["lũy kế", "accumulated", "%"]),
    Item("cfo", "cf", "LCTT thuần từ HĐKD",
         ids=["operating_cash_flow", "net_cash_flows_from_operating_activities", "cash_flow_from_operating_activities"],
         vi=["lưu chuyển tiền thuần từ hoạt động kinh doanh", "lưu chuyển tiền thuần từ các hoạt động sản xuất kinh doanh",
             "lưu chuyển tiền tệ ròng từ các hoạt động sản xuất kinh doanh", "lưu chuyển tiền thuần từ hđkd"],
         en=["net cash flows from operating", "net cash from operating", "cash flows from operating activities"],
         exclude=["trước", "before", "vốn lưu động", "working capital", "%"]),
    Item("cfi", "cf", "LCTT thuần từ HĐ đầu tư",
         ids=["investing_cash_flow", "net_cash_flows_from_investing_activities"],
         vi=["lưu chuyển tiền thuần từ hoạt động đầu tư", "lưu chuyển tiền tệ ròng từ hoạt động đầu tư"],
         en=["net cash flows from investing", "investing activities"], exclude=["%"]),
    Item("cff", "cf", "LCTT thuần từ HĐ tài chính",
         ids=["financing_cash_flow", "net_cash_flows_from_financing_activities"],
         vi=["lưu chuyển tiền thuần từ hoạt động tài chính", "lưu chuyển tiền tệ ròng từ hoạt động tài chính"],
         en=["net cash flows from financing", "financing activities"], exclude=["%"]),
    Item("capex", "cf", "Tiền chi mua sắm TSCĐ", ids=["purchase_of_fixed_assets", "capex", "capital_expenditure"],
         vi=["tiền chi để mua sắm, xây dựng tài sản cố định", "tiền chi để mua sắm", "mua sắm tài sản cố định",
             "mua sắm, xây dựng tscđ"],
         en=["purchase of fixed assets", "purchases of fixed assets", "acquisition of fixed assets", "capital expenditure"],
         exclude=["thanh lý", "disposal", "thu từ", "proceeds", "%"]),
    Item("dividends_paid", "cf", "Cổ tức đã trả", ids=["dividends_paid"],
         vi=["cổ tức, lợi nhuận đã trả cho chủ sở hữu", "cổ tức, lợi nhuận đã trả", "cổ tức đã trả"],
         en=["dividends paid"], exclude=["nhận", "received", "%"]),

    # ── Từ bảng chỉ số / thông tin cổ phiếu ──
    Item("shares_outstanding", "ratio", "Số CP lưu hành",
         ids=["outstanding_share", "shares_outstanding", "outstanding_shares", "issue_share"],
         vi=["số cổ phiếu lưu hành", "số cp lưu hành", "khối lượng cổ phiếu đang lưu hành", "số lượng cổ phiếu lưu hành"],
         en=["outstanding shares", "shares outstanding", "outstanding share"],
         exclude=["%", "tăng trưởng", "bình quân", "average"], unit="shares"),
]

ITEMS_BY_KEY: Dict[str, Item] = {it.key: it for it in CANONICAL_ITEMS}
PER_UNIT_KEYS = {k for k, it in ITEMS_BY_KEY.items() if it.unit != "vnd"}
STATEMENT_ITEMS: Dict[str, List[str]] = {}
for _it in CANONICAL_ITEMS:
    STATEMENT_ITEMS.setdefault(_it.statement, []).append(_it.key)


# ─────────────────────────────────────────────────────────────────────────────
# Chuyển mọi định dạng về dạng ma trận: cột "label" (vi), "label_en", "item_id" + cột kỳ
# ─────────────────────────────────────────────────────────────────────────────

def to_matrix(df: pd.DataFrame) -> Tuple[pd.DataFrame, List[int], List[int]]:
    """Trả về (bảng ma trận, VỊ TRÍ các cột kỳ đã sắp tăng dần theo thời gian, khóa kỳ tương ứng)."""
    if df is None or df.empty:
        return pd.DataFrame(), [], []
    # Nhãn kỳ suy biến: ≥ 4 cột kỳ nhưng tất cả cùng MỘT nhãn (vd 16 cột đều là "2018") →
    # không xác định được cột nào thuộc kỳ nào → bỏ bảng này thay vì gán nhầm số liệu.
    # (Kiểm tra TRƯỚC khi loại cột trùng.)
    if not isinstance(df.columns, pd.MultiIndex):
        parsed = [parse_period_key(c) for c in map(str, df.columns)
                  if str(c) not in ("item", "item_en", "item_id") and not re.search(r"_\d+$", str(c))]
        parsed = [k for k in parsed if k is not None]
        if len(parsed) >= 4 and len(set(parsed)) == 1:
            return pd.DataFrame(), [], []
    df = flatten_columns(df)
    id_cols = [c for c in ("item", "item_en", "item_id") if c in df.columns]

    if not id_cols:
        # Dạng bảng (mỗi dòng 1 kỳ) -> chuyển vị
        tab = order_tabular(df)
        if not all(isinstance(k, (int, np.integer)) for k in tab.index):
            return pd.DataFrame(), [], []
        skip = {c for c in tab.columns if norm_label(c) in
                {"năm", "nam", "year", "kỳ", "ky", "quý", "quy", "quarter", "cp", "ticker", "symbol",
                 "yearreport", "lengthreport", "source", "fetched_at"}}
        value_cols = [c for c in tab.columns if c not in skip]
        mat = tab[value_cols].T
        mat.columns = [key_to_label(k) for k in tab.index]
        mat.insert(0, "item", [str(c) for c in value_cols])
        df = mat.reset_index(drop=True)
        id_cols = ["item"]

    # Cột kỳ: đọc nhãn -> khóa kỳ, xác định theo VỊ TRÍ cột (không theo tên) vì nguồn có thể
    # trả nhiều cột cùng tên – vd bảng chỉ số VCI theo quý nhưng nhãn chỉ ghi năm ("2025" ×4).
    # Với mỗi kỳ chỉ giữ cột ĐẦU TIÊN (nguồn VCI xếp kỳ mới nhất trước).
    keyed: Dict[int, int] = {}
    for pos, c in enumerate(df.columns):
        if c in id_cols or _norm(c) in META_COLS | {"rownumber"}:
            continue
        if re.search(r"_\d+$", str(c)):          # cột trùng do nguồn tự đánh hậu tố
            continue
        k = parse_period_key(c)
        if k is not None and k not in keyed:
            keyed[k] = pos
    keys = sorted(keyed)
    return df, [keyed[k] for k in keys], keys


# ─────────────────────────────────────────────────────────────────────────────
# Khớp chỉ tiêu
# ─────────────────────────────────────────────────────────────────────────────

def _excluded(label: str, excl: List[str]) -> bool:
    plain = strip_accents(label)
    return any(e in label or strip_accents(e) in plain for e in excl)


def _find_row(mat: pd.DataFrame, item: Item) -> Optional[int]:
    ids = mat["item_id"].astype(str).str.lower().tolist() if "item_id" in mat.columns else []
    for want in item.ids:
        if want in ids:
            return ids.index(want)

    for col, patterns in (("item", item.vi), ("item_en", item.en)):
        if col not in mat.columns or not patterns:
            continue
        labels = [norm_label(x) for x in mat[col].tolist()]
        plains = [strip_accents(x) for x in labels]
        for pat in patterns:
            p, pp = pat.lower(), strip_accents(pat.lower())
            for mode in ("start", "contain"):
                for i, (lab, plain) in enumerate(zip(labels, plains)):
                    if not lab or _excluded(lab, item.exclude):
                        continue
                    hit = (lab.startswith(p) or plain.startswith(pp)) if mode == "start" else (p in lab or pp in plain)
                    if hit:
                        return i
    return None


def _unit_factor_from_labels(mat: pd.DataFrame) -> Optional[float]:
    text = " ".join(str(x) for x in mat.get("item", pd.Series(dtype=str)).tolist()).lower()
    if "tỷ đồng" in text or "(tỷ" in text:
        return 1e9
    if "triệu đồng" in text or "(triệu" in text:
        return 1e6
    return None


def canonicalize(df: pd.DataFrame, statement: Optional[str] = None,
                 unit_factor: Optional[float] = None) -> pd.DataFrame:
    """
    Chuẩn hóa một bảng BCTC thô về dạng rộng: index = khóa kỳ, cột = chỉ tiêu chuẩn.

    statement : "is" | "bs" | "cf" | "ratio" | None (None = thử mọi chỉ tiêu)
    unit_factor: hệ số quy đổi về VND nếu đã biết (vd 1e9 khi nguồn ghi "tỷ đồng").
    """
    mat, period_pos, keys = to_matrix(df)
    if mat.empty or not period_pos:
        return pd.DataFrame()
    wanted = CANONICAL_ITEMS if statement is None else [i for i in CANONICAL_ITEMS if i.statement == statement]
    out = {}
    for item in wanted:
        idx = _find_row(mat, item)
        if idx is None:
            continue
        vals = pd.to_numeric(mat.iloc[idx, period_pos], errors="coerce").to_numpy(dtype=float)
        out[item.key] = vals
    if not out:
        return pd.DataFrame()
    wide = pd.DataFrame(out, index=pd.Index(keys, name="period_key"))

    factor = unit_factor or _unit_factor_from_labels(mat)
    if factor:
        money = [c for c in wide.columns if c not in PER_UNIT_KEYS]
        wide[money] = wide[money] * factor
    return wide.dropna(how="all")


def infer_scale(wide: pd.DataFrame) -> float:
    """
    Đoán hệ số đơn vị khi nguồn không ghi rõ: tổng tài sản (hoặc doanh thu) của DN niêm yết
    luôn ≥ 10 tỷ VND. Trả về hệ số nhỏ nhất trong {1, 1e3, 1e6, 1e9} đưa trung vị về ≥ 1e10.
    """
    for col in ("total_assets", "equity", "revenue", "total_operating_income"):
        if col in wide.columns:
            med = wide[col].abs().median()
            if pd.notna(med) and med > 0:
                for f in (1.0, 1e3, 1e6, 1e9):
                    if med * f >= 1e10:
                        return f
    return 1.0


def apply_scale(wide: pd.DataFrame, factor: float) -> pd.DataFrame:
    if factor == 1.0 or wide.empty:
        return wide
    wide = wide.copy()
    money = [c for c in wide.columns if c not in PER_UNIT_KEYS]
    wide[money] = wide[money] * factor
    return wide


def wide_to_long(wide: pd.DataFrame, source_map: Optional[pd.DataFrame] = None) -> pd.DataFrame:
    if wide.empty:
        return pd.DataFrame(columns=["period_key", "item", "value", "source"])
    long = wide.reset_index().melt(id_vars="period_key", var_name="item", value_name="value").dropna(subset=["value"])
    if source_map is not None and not source_map.empty:
        src = source_map.reset_index().melt(id_vars="period_key", var_name="item", value_name="source")
        long = long.merge(src, on=["period_key", "item"], how="left")
    else:
        long["source"] = None
    return long


def long_to_wide(long: pd.DataFrame) -> Tuple[pd.DataFrame, pd.DataFrame]:
    if long is None or long.empty:
        return pd.DataFrame(), pd.DataFrame()
    wide = long.pivot_table(index="period_key", columns="item", values="value", aggfunc="first").sort_index()
    src = long.pivot_table(index="period_key", columns="item", values="source", aggfunc="first").sort_index()
    wide.index = wide.index.astype(int)
    src.index = src.index.astype(int)
    return wide, src
