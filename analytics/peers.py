"""
So sánh ngành (peer comparison).

Tính TRUNG VỊ các chỉ số P/E, P/B, ROE, Biên LN ròng, Nợ/VCSH của các doanh nghiệp
cùng nhóm ngành (lấy từ BASKETS trong data/ticker_directory.py), dùng dữ liệu thật
từ bảng chỉ số tài chính của từng mã.

Thay thế cho các hằng số cố định trước đây (P/E = 15, P/B = 1.5 cho mọi mã,
và số "trung vị ngành" gõ tay trong báo cáo PDF).
"""
from __future__ import annotations

import logging
from statistics import median
from typing import Any, Callable, Dict, List, Optional

import pandas as pd

from analytics.fundamental import FundamentalAnalyzer
from analytics.valuation import ValuationEngine
from data.ticker_directory import BASKETS

logger = logging.getLogger(__name__)

# Rổ chỉ số (không phải ngành) – bỏ qua khi tìm nhóm ngành
_INDEX_BASKET_MARKERS = ("Tất cả", "VN30", "HNX30")

# Lọc giá trị ngoại lai trước khi lấy trung vị
_BOUNDS = {
    "pe": (0, 100),
    "pb": (0, 20),
    "roe": (-100, 100),
    "net_margin": (-100, 100),
    "de": (0, 20),
}
MIN_PEERS = 3          # cần tối thiểu 3 DN có số liệu mới công bố trung vị
DEFAULT_MAX_PEERS = 8  # giới hạn số mã gọi API (vnstock giới hạn tần suất request)


def find_sector_basket(symbol: str) -> Optional[str]:
    """Tên nhóm ngành đầu tiên chứa mã (bỏ qua các rổ chỉ số VN30/HNX30)."""
    sym = symbol.upper().strip()
    for name, tickers in BASKETS.items():
        if any(m in name for m in _INDEX_BASKET_MARKERS):
            continue
        if sym in tickers:
            return name
    return None


def _clean_group_name(name: str) -> str:
    # Bỏ emoji ở đầu tên rổ: "🏦 Ngân hàng" -> "Ngân hàng"
    parts = name.split(" ", 1)
    return parts[1] if len(parts) == 2 and not parts[0].isalnum() else name


def _pct(v: Optional[float]) -> Optional[float]:
    if v is None:
        return None
    return v * 100 if abs(v) < 1.0 else v


def extract_peer_metrics(symbol: str, ratio_df: pd.DataFrame) -> Dict[str, Optional[float]]:
    """Đọc P/E, P/B, ROE, Biên LN ròng, Nợ/VCSH (kỳ mới nhất) từ bảng ratio của 1 mã."""
    if ratio_df is None or ratio_df.empty:
        return {}
    ve = ValuationEngine(symbol, 0, ratio_df=ratio_df)
    fa = FundamentalAnalyzer(None, None, None, ratio_df=ratio_df, symbol=symbol)

    def last(candidates: List[str]) -> Optional[float]:
        s = fa._series(fa.ratio_df, candidates)
        s = pd.to_numeric(s, errors="coerce").dropna()
        return float(s.iloc[-1]) if not s.empty else None

    pe = ve._col(ve.ratio_df, ["pe_ratio", "p/e", "pe", "price earning", "price to earnings"])
    pb = ve._col(ve.ratio_df, ["pb_ratio", "p/b", "pb", "price book", "price to book"])
    roe = fa.get_return_metrics().get("roe")
    margin = _pct(last(["net_profit_margin", "biên lợi nhuận ròng", "net margin", "netprofitmargin"]))
    de = last(["debt_to_equity", "debtPerEquity", "nợ/vcsh", "nợ/vốn chủ", "nợ trên vốn chủ"])
    return {"pe": pe, "pb": pb, "roe": roe, "net_margin": margin, "de": de}


def _robust_median(values: List[Optional[float]], key: str) -> Optional[float]:
    lo, hi = _BOUNDS[key]
    clean = [float(v) for v in values if v is not None and pd.notna(v) and lo < float(v) < hi]
    return round(median(clean), 2) if len(clean) >= MIN_PEERS else None


def compute_peer_stats(
    symbol: str,
    ratio_fetcher: Callable[[str], pd.DataFrame],
    max_peers: int = DEFAULT_MAX_PEERS,
) -> Dict[str, Any]:
    """
    Parameters
    ----------
    symbol        : mã cần so sánh
    ratio_fetcher : hàm(symbol) -> DataFrame chỉ số tài chính (vd. repo.get_financial_ratios)

    Returns
    -------
    dict: group, peers, n, pe, pb, roe, net_margin, de, n_<metric>
          (giá trị None nếu có ít hơn MIN_PEERS doanh nghiệp có số liệu)
    """
    basket = find_sector_basket(symbol)
    if basket is None:
        return {"group": None, "n": 0, "reason": "Mã chưa được phân loại vào nhóm ngành nào"}

    peers = [t for t in BASKETS[basket] if t != symbol.upper()][:max_peers]
    rows: List[Dict[str, Optional[float]]] = []
    used: List[str] = []
    for peer in peers:
        try:
            m = extract_peer_metrics(peer, ratio_fetcher(peer))
            if any(v is not None for v in m.values()):
                rows.append(m)
                used.append(peer)
        except Exception as exc:  # một mã lỗi không làm hỏng cả nhóm
            logger.debug("Peer %s failed: %s", peer, exc)

    out: Dict[str, Any] = {"group": _clean_group_name(basket), "peers": used, "n": len(used)}
    for key in _BOUNDS:
        vals = [r.get(key) for r in rows]
        out[key] = _robust_median(vals, key)
        lo, hi = _BOUNDS[key]
        out[f"n_{key}"] = sum(1 for v in vals if v is not None and lo < float(v) < hi)
    return out
