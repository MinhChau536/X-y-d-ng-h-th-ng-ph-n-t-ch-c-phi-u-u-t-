"""
Tiện ích nhận diện & sắp xếp kỳ báo cáo tài chính.

Vấn đề cũ: code lấy `.iloc[-1]` làm "kỳ mới nhất" và `.iloc[-2]` làm "kỳ trước"
mà không kiểm tra thứ tự kỳ. Với dữ liệu quý, phép so sánh đó là QoQ (quý liền
trước) chứ không phải YoY, và nếu nguồn trả về kỳ mới nhất đứng đầu thì "mới nhất"
thực ra lại là kỳ cũ nhất.

Khóa kỳ (period key) = năm * 10 + quý   (quý 1..4; báo cáo năm dùng 0)
  ví dụ Q3/2025 -> 20253, năm 2024 -> 20240
=> sắp xếp số học đúng thứ tự thời gian và cùng kỳ năm trước = key - 10.
"""
from __future__ import annotations

import re
from typing import List, Optional, Tuple

import pandas as pd

META_COLS = {"item", "item_en", "item_id", "symbol", "source", "fetched_at",
             "unit", "levels", "level", "ticker", "cp", "report_type"}

_YEAR_NAMES = {"năm", "nam", "year", "yearreport", "fiscalyear"}
_QUARTER_NAMES = {"kỳ", "ky", "quý", "quy", "quarter", "lengthreport", "period_quarter"}


def flatten_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Gộp MultiIndex columns (vnstock VCI trả về dạng này cho bảng ratio) thành chuỗi."""
    if df is None or df.empty:
        return df if df is not None else pd.DataFrame()
    if isinstance(df.columns, pd.MultiIndex):
        df = df.copy()
        df.columns = [
            " ".join(str(x) for x in col if str(x) and not str(x).startswith("Unnamed")).strip()
            for col in df.columns
        ]
    else:
        df = df.copy()
        df.columns = [str(c) for c in df.columns]
    # Nguồn có thể trả về tên cột trùng nhau → giữ cột đầu tiên
    if df.columns.duplicated().any():
        df = df.loc[:, ~df.columns.duplicated()]
    return df


def _norm(name: str) -> str:
    return str(name).strip().lower().replace("_", "").replace(" ", "")


def _last_token(name: str) -> str:
    parts = str(name).strip().lower().split()
    return parts[-1] if parts else ""


def parse_period_key(label) -> Optional[int]:
    """Đọc nhãn kỳ dạng '2024-Q3', 'Q3/2024', '2024Q3', 'Q3 2024', '2024' → khóa số."""
    if label is None:
        return None
    txt = str(label).strip().upper()
    m_year = re.search(r"(19|20)\d{2}", txt)
    if not m_year:
        return None
    year = int(m_year.group(0))
    rest = txt[:m_year.start()] + " " + txt[m_year.end():]
    m_q = re.search(r"Q\s*([1-4])", rest) or re.search(r"(?:^|[^0-9])([1-4])(?:[^0-9]|$)", rest)
    q = int(m_q.group(1)) if m_q else 0
    return year * 10 + q


def key_to_label(key) -> str:
    try:
        k = int(key)
    except (TypeError, ValueError):
        return str(key)
    year, q = divmod(k, 10)
    return f"Q{q}/{year}" if 1 <= q <= 4 else str(year)


def _find_col(df: pd.DataFrame, names: set) -> Optional[str]:
    for c in df.columns:
        if _norm(c) in names or _last_token(c) in names:
            return c
    return None


def order_tabular(df: pd.DataFrame) -> pd.DataFrame:
    """
    Bảng dạng mỗi dòng = 1 kỳ (có cột Năm / Kỳ): sắp xếp tăng dần theo thời gian
    và đặt index = khóa kỳ. Không nhận diện được thì giữ nguyên.
    """
    if df is None or df.empty:
        return df
    year_col = _find_col(df, _YEAR_NAMES)
    if year_col is None:
        return df
    years = pd.to_numeric(df[year_col], errors="coerce")
    q_col = _find_col(df, _QUARTER_NAMES)
    if q_col is not None:
        qs = pd.to_numeric(df[q_col], errors="coerce").fillna(0)
        qs = qs.where(qs.between(1, 4), 0)
    else:
        qs = pd.Series(0, index=df.index)
    keys = years * 10 + qs
    if keys.isna().all():
        return df
    out = df.copy()
    out.index = keys.astype("Int64")
    out = out[out.index.notna()]
    out = out[~out.index.duplicated(keep="last")].sort_index()
    out.index = out.index.astype(int)
    return out


def ordered_period_columns(df: pd.DataFrame) -> Tuple[List[str], List[Optional[int]]]:
    """
    Bảng dạng ma trận (mỗi dòng = 1 chỉ tiêu, mỗi cột = 1 kỳ): trả về danh sách cột kỳ
    theo đúng thứ tự thời gian cùng khóa kỳ tương ứng (None nếu không đọc được).
    """
    cols = [c for c in df.columns if _norm(c) not in META_COLS]
    keyed = [(c, parse_period_key(c)) for c in cols]
    if keyed and all(k is not None for _, k in keyed):
        keyed.sort(key=lambda x: x[1])
        return [c for c, _ in keyed], [k for _, k in keyed]
    cols_sorted = sorted(cols)
    return cols_sorted, [None] * len(cols_sorted)


def growth_vs_prior(series: pd.Series) -> dict:
    """
    Tăng trưởng của kỳ mới nhất.

    - Có khóa kỳ & là quý  -> so với CÙNG QUÝ năm trước (YoY)
    - Có khóa kỳ & là năm  -> so với năm trước
    - Không xác định được  -> so với kỳ liền trước (ghi rõ basis để người đọc biết)
    """
    s = pd.to_numeric(series, errors="coerce").dropna()
    res = {"pct": None, "basis": None, "latest_period": None, "compare_period": None}
    if len(s) < 2:
        return res

    latest_key = s.index[-1]
    latest = float(s.iloc[-1])
    prior = None

    is_int_key = all(isinstance(k, (int,)) or (hasattr(k, "is_integer") and float(k).is_integer())
                     for k in s.index) and all(int(k) > 10000 for k in s.index)
    if is_int_key:
        lk = int(latest_key)
        target = lk - 10
        idx = [int(k) for k in s.index]
        if target in idx:
            prior = float(s.iloc[idx.index(target)])
            res["basis"] = "YoY (cùng kỳ năm trước)" if lk % 10 else "So với năm trước"
            res["compare_period"] = key_to_label(target)
        res["latest_period"] = key_to_label(lk)
        if prior is None:
            prior = float(s.iloc[-2])
            res["basis"] = "So với kỳ liền trước (thiếu số liệu cùng kỳ năm trước)"
            res["compare_period"] = key_to_label(int(s.index[-2]))
    else:
        prior = float(s.iloc[-2])
        res["basis"] = "So với kỳ liền trước (không xác định được kỳ báo cáo)"

    if prior is not None and prior != 0:
        res["pct"] = (latest - prior) / abs(prior) * 100
    return res
