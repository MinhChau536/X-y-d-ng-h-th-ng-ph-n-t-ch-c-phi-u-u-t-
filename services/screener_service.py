"""
Bộ lọc cổ phiếu (screener) & so sánh nhiều mã.

Mỗi mã được tính một "hồ sơ chỉ số" từ dữ liệu thật:
  giá & hiệu suất (từ chuỗi giá ghép DNSE + lịch sử), chỉ số tính từ BCTC năm gần nhất,
  định giá tại giá hiện tại, Piotroski F-score, Altman Z''-score.
Hồ sơ được lưu cache theo ngày để lọc lại nhanh. Do giới hạn tần suất gọi API của nguồn
dữ liệu, nên dùng bộ lọc trên từng nhóm ngành / rổ (≈ 10–30 mã) thay vì toàn thị trường;
script cập nhật hằng ngày có thể tính trước cho các rổ thường dùng.
"""
from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from typing import Any, Callable, Dict, Iterable, List, Optional

import numpy as np
import pandas as pd

from data.cache import cache

logger = logging.getLogger(__name__)

PROFILE_COLUMNS = {
    "symbol": "Mã", "price": "Giá", "change_1m": "% 1 tháng", "change_3m": "% 3 tháng", "change_1y": "% 12 tháng",
    "market_cap": "Vốn hóa", "pe": "P/E", "pb": "P/B", "ev_ebitda": "EV/EBITDA", "dividend_yield": "Tỷ suất cổ tức %",
    "roe": "ROE %", "roa": "ROA %", "net_margin": "Biên LN ròng %", "gross_margin": "Biên LN gộp %",
    "revenue_growth": "Tăng trưởng DT %", "net_income_growth": "Tăng trưởng LNST %",
    "debt_to_equity": "Nợ vay/VCSH", "current_ratio": "Thanh toán hiện hành",
    "fscore": "F-score", "zscore": "Z''-score", "fin_period": "Kỳ BCTC", "error": "Ghi chú",
}

# Bộ lọc mẫu (chiến lược phổ biến) – (cột, toán tử, ngưỡng)
PRESETS: Dict[str, List[tuple]] = {
    "Giá trị (Value)": [("pe", "<=", 12), ("pb", "<=", 1.5), ("roe", ">=", 12)],
    "Tăng trưởng (Growth)": [("revenue_growth", ">=", 15), ("net_income_growth", ">=", 15), ("roe", ">=", 15)],
    "Chất lượng (Quality)": [("roe", ">=", 18), ("debt_to_equity", "<=", 1), ("fscore", ">=", 6)],
    "Cổ tức cao": [("dividend_yield", ">=", 5), ("debt_to_equity", "<=", 1.5)],
    "Động lượng (Momentum)": [("change_3m", ">=", 10), ("change_1y", ">=", 20)],
}


def build_profile(symbol: str, svc_factory: Callable[[str], Any]) -> Dict[str, Any]:
    """Hồ sơ chỉ số của một mã (svc_factory(symbol) -> StockService)."""
    out: Dict[str, Any] = {"symbol": symbol}
    try:
        svc = svc_factory(symbol)
        px = svc.get_price_df()
        if px is not None and not px.empty:
            c = px["close"].astype(float)
            out["price"] = float(c.iloc[-1])
            for key, n in (("change_1m", 21), ("change_3m", 63), ("change_1y", 250)):
                out[key] = (float(c.iloc[-1]) / float(c.iloc[-n - 1]) - 1) * 100 if len(c) > n else None
        summ = svc.financial_summary("year")
        ratios = summ.get("ratios", pd.DataFrame())
        if ratios is not None and not ratios.empty:
            last = ratios.iloc[-1]
            for k in ("roe", "roa", "net_margin", "gross_margin", "revenue_growth", "net_income_growth",
                      "debt_to_equity", "current_ratio"):
                v = last.get(k)
                out[k] = float(v) if v is not None and pd.notna(v) else None
            from analytics.period_utils import key_to_label
            out["fin_period"] = key_to_label(ratios.index[-1])
        val = summ.get("valuation") or {}
        for k in ("pe", "pb", "ev_ebitda", "dividend_yield", "market_cap"):
            out[k] = val.get(k)
        out["fscore"] = (summ.get("piotroski") or {}).get("score")
        out["zscore"] = (summ.get("altman") or {}).get("score")
    except Exception as exc:
        out["error"] = str(exc)[:120]
        logger.debug("profile %s failed: %s", symbol, exc)
    return out


class ScreenerService:

    def __init__(self, svc_factory: Optional[Callable[[str], Any]] = None, use_cache: bool = True):
        if svc_factory is None:
            from services.stock_service import StockService
            svc_factory = lambda s: StockService(s, days=400, fin_period="year", fin_years=6)  # noqa: E731
        self.svc_factory = svc_factory
        self.use_cache = use_cache

    def profile(self, symbol: str, force: bool = False) -> Dict[str, Any]:
        key = f"screen:{symbol}:{date.today()}"
        if self.use_cache and not force:
            hit = cache.get(key)
            if hit:
                return hit
        p = build_profile(symbol, self.svc_factory)
        if self.use_cache and "error" not in p:
            cache.set(key, p, ttl=86400)
        return p

    def run(self, symbols: Iterable[str], max_workers: int = 3, force: bool = False,
            progress: Optional[Callable[[int, int], None]] = None) -> pd.DataFrame:
        syms = list(dict.fromkeys(s.upper().strip() for s in symbols if s))
        rows: List[Dict[str, Any]] = []
        with ThreadPoolExecutor(max_workers=max_workers) as ex:
            for i, res in enumerate(ex.map(lambda s: self.profile(s, force), syms), start=1):
                rows.append(res)
                if progress:
                    progress(i, len(syms))
        return pd.DataFrame(rows)

    @staticmethod
    def apply_filters(df: pd.DataFrame, filters: List[tuple]) -> pd.DataFrame:
        """filters: [(cột, toán tử, ngưỡng)], toán tử: >=, <=, >, <. Mã thiếu số liệu bị loại."""
        if df.empty:
            return df
        mask = pd.Series(True, index=df.index)
        ops = {">=": np.greater_equal, "<=": np.less_equal, ">": np.greater, "<": np.less}
        for col, op, thr in filters:
            if col not in df.columns:
                mask &= False
                continue
            vals = pd.to_numeric(df[col], errors="coerce")
            mask &= vals.notna() & ops[op](vals, thr)
        return df[mask]

    @staticmethod
    def rank(df: pd.DataFrame, weights: Optional[Dict[str, float]] = None) -> pd.DataFrame:
        """
        Xếp hạng tổng hợp theo phân vị: mỗi tiêu chí đổi thành thứ hạng phần trăm trong nhóm
        (chỉ số "thấp là tốt" như P/E, Nợ/VCSH được đảo chiều), rồi lấy bình quân có trọng số.
        """
        if df.empty:
            return df
        weights = weights or {"roe": 1, "revenue_growth": 1, "net_income_growth": 1, "pe": 1, "pb": 0.5,
                              "debt_to_equity": 0.5, "change_3m": 0.5}
        lower_better = {"pe", "pb", "ev_ebitda", "debt_to_equity"}
        parts, wsum = [], 0.0
        for col, w in weights.items():
            if col not in df.columns:
                continue
            vals = pd.to_numeric(df[col], errors="coerce")
            if col in ("pe", "pb", "ev_ebitda"):
                vals = vals.where(vals > 0)       # P/E âm (thua lỗ) không được coi là "rẻ"
            pct = vals.rank(pct=True, ascending=col not in lower_better)
            parts.append(pct.fillna(0) * w)
            wsum += w
        out = df.copy()
        out["rank_score"] = (sum(parts) / wsum * 100).round(1) if parts else np.nan
        return out.sort_values("rank_score", ascending=False)


def compare(symbols: List[str], svc_factory: Optional[Callable[[str], Any]] = None) -> Dict[str, Any]:
    """So sánh nhiều mã: bảng chỉ số + chuỗi giá chuẩn hóa (gốc = 100)."""
    scr = ScreenerService(svc_factory)
    table = scr.run(symbols)
    prices = {}
    for s in symbols:
        try:
            px = scr.svc_factory(s).get_price_df()
            if px is not None and not px.empty:
                prices[s] = px.set_index("timestamp")["close"].astype(float)
        except Exception:
            continue
    norm = pd.DataFrame(prices).dropna(how="all")
    if not norm.empty:
        norm = norm.ffill().dropna()
        norm = norm / norm.iloc[0] * 100 if not norm.empty else norm
    return {"table": table, "normalized_prices": norm}
