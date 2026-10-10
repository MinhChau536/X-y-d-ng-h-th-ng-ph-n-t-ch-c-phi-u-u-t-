"""
Xuất BCTC chuẩn hóa nhiều năm + chỉ số tài chính + nguồn dữ liệu ra file Excel (.xlsx).

Các sheet:
  KQKD, CDKT, LCTT  – chỉ tiêu × kỳ (tỷ đồng), đúng thứ tự trình bày
  Chi_so            – các chỉ số tính từ BCTC theo nhóm
  Nguon_du_lieu     – nguồn của từng ô (vnstock_vci / vnstock_kbs / vietstock / pdf)
  Bang_goc_<nguồn>  – bảng thô gốc của từng nguồn (nếu có), để đối chiếu
"""
from __future__ import annotations

import io
from typing import Any, Dict, Optional

import pandas as pd

from analytics.financial_ratios import RATIO_META
from analytics.period_utils import key_to_label
from data.financial_mapping import ITEMS_BY_KEY, PER_UNIT_KEYS, STATEMENT_ITEMS

_SHEETS = {"is": "KQKD", "bs": "CDKT", "cf": "LCTT"}


def statement_table(data: pd.DataFrame, statement: str, unit: float = 1e9) -> pd.DataFrame:
    """Bảng trình bày: dòng = chỉ tiêu (nhãn tiếng Việt), cột = kỳ; tiền tệ chia theo `unit`."""
    keys = [k for k in STATEMENT_ITEMS.get(statement, []) if k in data.columns]
    if not keys:
        return pd.DataFrame()
    rows = []
    for k in keys:
        series = data[k]
        if series.isna().all():
            continue
        scale = 1.0 if k in PER_UNIT_KEYS else unit
        row = {"Chỉ tiêu": ITEMS_BY_KEY[k].label_vi}
        for pk, v in series.items():
            row[key_to_label(pk)] = (v / scale) if pd.notna(v) else None
        rows.append(row)
    return pd.DataFrame(rows)


def export_financials(symbol: str, financials: Dict[str, Any], summary: Optional[Dict[str, Any]] = None,
                      unit: float = 1e9) -> bytes:
    data: pd.DataFrame = financials.get("data", pd.DataFrame())
    sources: pd.DataFrame = financials.get("sources", pd.DataFrame())
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as xw:
        info = pd.DataFrame({
            "Thông tin": ["Mã", "Kỳ", "Đơn vị tiền tệ", "Thời điểm lấy dữ liệu", "Ghi chú"],
            "Giá trị": [symbol, "Năm" if financials.get("period") == "year" else "Quý",
                        "Tỷ đồng (trừ EPS, BVPS: đồng/cp; số CP: cổ phiếu)", financials.get("fetched_at", ""),
                        "Số liệu chuẩn hóa từ nhiều nguồn; xem sheet Nguon_du_lieu để biết nguồn từng ô."],
        })
        info.to_excel(xw, sheet_name="Thong_tin", index=False)
        for st, name in _SHEETS.items():
            t = statement_table(data, st, unit)
            if not t.empty:
                t.to_excel(xw, sheet_name=name, index=False)
        if summary and summary.get("ratios") is not None and not summary["ratios"].empty:
            r = summary["ratios"]
            rows = []
            for key, (label, group, fmt, _) in RATIO_META.items():
                if key not in r.columns:
                    continue
                scale = unit if fmt == "vnd" and key == "fcf" else 1.0
                row = {"Nhóm": group, "Chỉ số": label, "Đơn vị": {"%": "%", "x": "lần", "days": "ngày",
                                                                     "vnd": "tỷ đồng" if key == "fcf" else "đồng"}.get(fmt, "")}
                for pk, v in r[key].items():
                    row[key_to_label(pk)] = (v / scale) if pd.notna(v) else None
                rows.append(row)
            pd.DataFrame(rows).to_excel(xw, sheet_name="Chi_so", index=False)
        if sources is not None and not sources.empty:
            s = sources.copy()
            s.index = [key_to_label(k) for k in s.index]
            s.columns = [ITEMS_BY_KEY[c].label_vi if c in ITEMS_BY_KEY else c for c in s.columns]
            s.T.to_excel(xw, sheet_name="Nguon_du_lieu")
        for st, by_src in (financials.get("raw") or {}).items():
            for src, raw in by_src.items():
                name = f"Goc_{_SHEETS.get({'income_statement': 'is', 'balance_sheet': 'bs', 'cash_flow': 'cf'}.get(st, ''), st)}_{src}"[:31]
                try:
                    from components.ui import unique_columns
                    unique_columns(raw).to_excel(xw, sheet_name=name, index=False)
                except Exception:
                    pass
        for ws in xw.book.worksheets:
            ws.freeze_panes = "B2"
            for col in ws.columns:
                width = max(len(str(c.value or "")) for c in col[:50])
                ws.column_dimensions[col[0].column_letter].width = min(max(10, width + 2), 60)
                for c in col[1:]:
                    if isinstance(c.value, float):
                        c.number_format = "#,##0.00"
    return buf.getvalue()
