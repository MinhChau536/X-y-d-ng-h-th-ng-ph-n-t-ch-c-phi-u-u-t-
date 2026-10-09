"""Tính các chỉ số tài chính CƠ BẢN từ dữ liệu do fetch_financials.get_financials() trả về.
Không chấm điểm, không định giá. Thiếu dữ liệu => NaN (không ép về 0).

    from fetch_financials import get_financials
    from ratios import get_ratios
    d = get_financials("VNM")
    r = get_ratios(d)      # r["ratios"] (dòng = năm), r["sector"], r["mapping"], r["inputs"]
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from fetch_financials import _norm

SECTOR_LABEL = {"corporate": "Doanh nghiệp phi tài chính", "bank": "Ngân hàng",
                "securities": "Công ty chứng khoán", "insurance": "Bảo hiểm"}
SECTOR_MARKERS = [("bank", ["Thu nhập lãi thuần", "Tiền gửi của khách hàng"]),
                  ("securities", ["Doanh thu hoạt động môi giới chứng khoán"]),
                  ("insurance", ["Doanh thu phí bảo hiểm"])]

# khái niệm -> các tên chỉ tiêu ứng viên (item_name gốc trong dataset, theo thứ tự ưu tiên)
_BS = {"total_assets": ["TỔNG TÀI SẢN"], "total_liabilities": ["NỢ PHẢI TRẢ", "Tổng nợ phải trả"],
       "equity": ["VỐN CHỦ SỞ HỮU", "Vốn chủ sở hữu"]}
_BS_CORP = {"current_assets": ["TÀI SẢN NGẮN HẠN"], "cash": ["Tiền và tương đương tiền"],
            "inventory": ["Hàng tồn kho, ròng", "Hàng tồn kho"], "receivables": ["Các khoản phải thu"],
            "current_liabilities": ["Nợ ngắn hạn"], "short_term_debt": ["Vay ngắn hạn"],
            "long_term_debt": ["Vay dài hạn"]}
_BS_BANK = {"customer_deposits": ["Tiền gửi của khách hàng"]}
_CF = {"cfo": ["Lưu chuyển tiền thuần từ các hoạt động sản xuất kinh doanh"],
       "capex": ["Tiền mua tài sản cố định và các tài sản dài hạn khác"]}
_INC = {
    "corporate": {"revenue": ["Doanh số thuần"], "cogs": ["Giá vốn hàng bán"], "gross_profit": ["Lãi gộp"],
                  "interest_expense": ["Trong đó: Chi phí lãi vay"], "profit_before_tax": ["Lãi/(lỗ) ròng trước thuế"],
                  "net_profit": ["Lãi/(lỗ) thuần sau thuế", "Lợi nhuận sau thuế", "Lợi nhuận kế toán sau thuế"],
                  "ebit": ["EBIT"], "ebitda": ["EBITDA"]},
    "bank": {"revenue": ["Tổng thu nhập hoạt động"], "net_interest_income": ["Thu nhập lãi thuần"],
             "opex": ["Chi phí hoạt động"], "provision": ["Chi phí dự phòng rủi ro tín dụng"],
             "profit_before_tax": ["Tổng lợi nhuận trước thuế"], "net_profit": ["Lợi nhuận sau thuế"]},
    "securities": {"revenue": ["Doanh thu hoạt động"], "net_profit": ["Lợi nhuận kế toán sau thuế", "Lợi nhuận sau thuế"]},
    "insurance": {"revenue": ["Doanh thu thuần từ hoạt động kinh doanh bảo hiểm", "Doanh thu phí bảo hiểm thuần"],
                  "net_profit": ["Lợi nhuận sau thuế thu nhập doanh nghiệp",
                                 "Lợi nhuận sau thuế của chủ sở hữu, tập đoàn"]},
}
LABEL = {"balance_sheet": "Bảng cân đối kế toán", "income_statement": "Kết quả kinh doanh", "cash_flow": "Lưu chuyển tiền tệ"}

PERCENT = {"ROE (BQ)", "ROE (cuối kỳ)", "ROA (BQ)", "Biên LN ròng", "Vốn CSH/Tổng TS", "Nợ/Tổng TS",
           "Tăng trưởng DT", "Tăng trưởng LNST", "Tăng trưởng Tổng TS", "Tăng trưởng VCSH", "Biên LN gộp",
           "Biên EBIT", "Biên EBITDA", "CFO/Doanh thu", "FCF/Doanh thu", "CIR", "Chi phí dự phòng/Thu nhập HĐ",
           "Thu nhập lãi thuần/Thu nhập HĐ", "Tăng trưởng thu nhập lãi thuần", "Tăng trưởng tiền gửi KH",
           "Tăng trưởng LNTT"}


def _pick(wide: pd.DataFrame, cands: list[str]):
    if wide is None or wide.empty:
        return None, None
    for n in cands:
        k = _norm(n)
        if k in wide.index and wide.loc[k].notna().any():
            return wide.loc[k], k
    return None, None


def _detect_sector(wides: dict) -> str:
    present = set()
    for w in wides.values():
        if w is not None and not w.empty:
            present |= set(w.index[w.notna().any(axis=1)])
    for sector, markers in SECTOR_MARKERS:
        if any(_norm(m) in present for m in markers):
            return sector
    return "corporate"


def _concepts(wides: dict, sector: str):
    spec = {"balance_sheet": {**_BS, **(_BS_CORP if sector == "corporate" else _BS_BANK if sector == "bank" else {})},
            "income_statement": _INC[sector], "cash_flow": _CF}
    cols, mapping = {}, []
    for st, concepts in spec.items():
        for concept, cands in concepts.items():
            s, name = _pick(wides.get(st), cands)
            mapping.append({"Khái niệm": concept, "Báo cáo": LABEL[st],
                            "Chỉ tiêu trong dataset": name or "— (không có dữ liệu)"})
            if s is not None:
                cols[concept] = s
    c = pd.DataFrame(cols)
    if c.empty:
        raise ValueError("Không trích được chỉ tiêu nào để tính tỷ số.")
    c.index = c.index.astype(int)
    c = c.sort_index().dropna(how="all")
    c = c.reindex(range(int(c.index.min()), int(c.index.max()) + 1))   # năm liên tục để YoY/bình quân đúng
    c.index.name = "year"
    if {"cfo", "capex"} <= set(c.columns):
        c["fcf"] = c["cfo"] - c["capex"].abs()
    return c, pd.DataFrame(mapping)


def _col(c, n):
    return c[n] if n in c.columns else pd.Series(np.nan, index=c.index, dtype=float)


def _div(a, b):
    return a / b.where(b != 0)


def _avg(s):
    return (s + s.shift(1)) / 2


def _yoy(s):
    p = s.shift(1)
    return s / p.where(p > 0) - 1        # kỳ gốc <= 0 => NaN


def _sum(*s):
    return pd.concat(s, axis=1).sum(axis=1, min_count=1)


def _calc(c: pd.DataFrame, sector: str) -> pd.DataFrame:
    npf, rev, ta, eq, tl = (_col(c, k) for k in ("net_profit", "revenue", "total_assets", "equity", "total_liabilities"))
    r = pd.DataFrame(index=c.index)
    r["ROE (BQ)"] = _div(npf, _avg(eq))
    r["ROE (cuối kỳ)"] = _div(npf, eq)
    r["ROA (BQ)"] = _div(npf, _avg(ta))
    r["Biên LN ròng"] = _div(npf, rev)
    r["Vốn CSH/Tổng TS"] = _div(eq, ta)
    r["Đòn bẩy TC (TS/VCSH)"] = _div(ta, eq)
    r["Nợ/Vốn CSH"] = _div(tl, eq)
    r["Nợ/Tổng TS"] = _div(tl, ta)
    r["Tăng trưởng DT"], r["Tăng trưởng LNST"] = _yoy(rev), _yoy(npf)
    r["Tăng trưởng Tổng TS"], r["Tăng trưởng VCSH"] = _yoy(ta), _yoy(eq)
    if sector == "corporate":
        cogs = _col(c, "cogs").abs()
        gp = _col(c, "gross_profit").fillna(rev - cogs)
        intexp = _col(c, "interest_expense").abs()
        ebit = _col(c, "ebit").fillna(_col(c, "profit_before_tax") + intexp)
        ebitda, ca, cl = _col(c, "ebitda"), _col(c, "current_assets"), _col(c, "current_liabilities")
        inv, cash, rec = _col(c, "inventory"), _col(c, "cash"), _col(c, "receivables")
        debt = _sum(_col(c, "short_term_debt"), _col(c, "long_term_debt"))
        cfo = _col(c, "cfo")
        turn = _div(cogs, _avg(inv))
        r["Biên LN gộp"], r["Biên EBIT"], r["Biên EBITDA"] = _div(gp, rev), _div(ebit, rev), _div(ebitda, rev)
        r["Thanh toán hiện hành"], r["Thanh toán nhanh"] = _div(ca, cl), _div(ca - inv, cl)
        r["Nợ vay/Vốn CSH"] = _div(debt, eq)
        r["Nợ vay ròng/EBITDA"] = _div(debt - cash, ebitda.where(ebitda > 0))
        r["Khả năng trả lãi (EBIT/Lãi vay)"] = _div(ebit, intexp)
        r["Vòng quay tổng TS"] = _div(rev, _avg(ta))
        r["Vòng quay HTK"] = turn
        r["Số ngày tồn kho"] = _div(pd.Series(365.0, index=c.index), turn)
        r["Số ngày thu tiền"] = 365.0 * _div(_avg(rec), rev)
        r["CFO/LNST"] = _div(cfo, npf.where(npf > 0))
        r["CFO/Doanh thu"], r["FCF/Doanh thu"] = _div(cfo, rev), _div(_col(c, "fcf"), rev)
    elif sector == "bank":
        r["CIR"] = _div(_col(c, "opex").abs(), rev)
        r["Chi phí dự phòng/Thu nhập HĐ"] = _div(_col(c, "provision").abs(), rev)
        r["Thu nhập lãi thuần/Thu nhập HĐ"] = _div(_col(c, "net_interest_income"), rev)
        r["Tăng trưởng thu nhập lãi thuần"] = _yoy(_col(c, "net_interest_income"))
        r["Tăng trưởng tiền gửi KH"] = _yoy(_col(c, "customer_deposits"))
        r["Tăng trưởng LNTT"] = _yoy(_col(c, "profit_before_tax"))
    return r.replace([np.inf, -np.inf], np.nan)


def get_ratios(data: dict, n_years: int | None = None) -> dict:
    """data: kết quả của get_financials(). Tính trên TOÀN BỘ lịch sử rồi mới cắt n_years cuối
    (cần năm trước để tính tăng trưởng và số dư bình quân)."""
    wides = {st: data[st] for st in ("balance_sheet", "income_statement", "cash_flow")}
    sector = _detect_sector(wides)
    c, mapping = _concepts(wides, sector)
    r = _calc(c, sector)
    if n_years:
        r, c = r.tail(n_years), c.tail(n_years)
    return {"symbol": data["symbol"], "sector": sector, "sector_label": SECTOR_LABEL[sector],
            "ratios": r, "mapping": mapping, "inputs": c}
