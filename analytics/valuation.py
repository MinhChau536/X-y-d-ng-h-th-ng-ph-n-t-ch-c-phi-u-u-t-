"""
Valuation analysis engine.

Methods:
  - P/E, P/B relative valuation
  - EV/EBITDA (when data available)
  - Simplified DCF
  - DDM (for dividend-paying stocks)
  - 3-scenario valuation (bear/base/bull)
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from analytics.period_utils import flatten_columns, order_tabular, ordered_period_columns
from config.constants import FUNDAMENTAL_THRESHOLDS as THR

logger = logging.getLogger(__name__)


def _s(v) -> Optional[float]:
    try:
        return None if pd.isna(v) else float(v)
    except (TypeError, ValueError):
        return None


class ValuationEngine:
    """
    Compute stock valuation estimates.

    Parameters
    ----------
    symbol         : Ticker
    current_price  : Latest market price
    ratio_df       : Financial ratio DataFrame from provider
    is_df          : Income Statement
    bs_df          : Balance Sheet
    shares_outstanding : Number of shares
    market_cap     : Market cap (VND)
    peer_stats     : Trung vị chỉ số của nhóm ngành (analytics.peers.compute_peer_stats)
    """

    # Chỉ dùng khi KHÔNG lấy được dữ liệu ngành – được ghi rõ trong kết quả
    MARKET_DEFAULT_PE = 15.0
    MARKET_DEFAULT_PB = 1.5

    def __init__(
        self,
        symbol: str,
        current_price: float,
        ratio_df: pd.DataFrame = None,
        is_df: pd.DataFrame = None,
        bs_df: pd.DataFrame = None,
        shares_outstanding: Optional[float] = None,
        market_cap: Optional[float] = None,
        peer_stats: Optional[Dict[str, Any]] = None,
        eps_override: Optional[float] = None,
        bvps_override: Optional[float] = None,
    ):
        self.symbol = symbol
        # On VN exchanges, quotes < 1000 are in k VND (e.g. 19.0 = 19,000 VND)
        p = float(current_price) if current_price else 0.0
        self.price = (p * 1000.0) if (0 < p < 1000.0) else p
        self.ratio_df = order_tabular(flatten_columns(ratio_df))
        self.is_df = order_tabular(flatten_columns(is_df))
        self.bs_df = order_tabular(flatten_columns(bs_df))
        self.shares = shares_outstanding
        self.market_cap = market_cap
        self.peer_stats = peer_stats or {}
        # EPS/BVPS tính từ BCTC (TTM) được ưu tiên hơn số dựng sẵn của nhà cung cấp
        self.eps_override = eps_override if eps_override and eps_override > 0 else None
        self.bvps_override = bvps_override if bvps_override and bvps_override > 0 else None

    def _sector_multiple(self, key: str, default: float):
        """Trả về (giá trị, nguồn) cho P/E hoặc P/B tham chiếu."""
        v = self.peer_stats.get(key)
        if v is not None and v > 0:
            group = self.peer_stats.get("group", "ngành")
            n = self.peer_stats.get(f"n_{key}", self.peer_stats.get("n", 0))
            return float(v), f"Trung vị {group} ({n} DN)"
        return default, "Mặc định thị trường (không đủ dữ liệu ngành)"

    # ─────────────────── Column finder ───────────────────────────────────────

    @staticmethod
    def _match(candidate: str, target: str) -> bool:
        c_clean = candidate.lower().replace("_", "").replace(" ", "").replace("/", "").replace("%", "")
        t_clean = target.lower().replace("_", "").replace(" ", "").replace("/", "").replace("%", "")
        if c_clean == t_clean:
            return True
        if c_clean in {"pe", "pb", "ps", "eps"}:
            return t_clean.startswith(c_clean) or t_clean.endswith(c_clean)
        if len(c_clean) >= 4 and c_clean in t_clean:
            return True
        if len(t_clean) >= 4 and t_clean in c_clean:
            return True
        return False

    def _col(self, df: pd.DataFrame, names: List[str]) -> Optional[float]:
        if df is None or df.empty:
            return None

        # 1. Tabular format (columns match name)
        for n in names:
            for c in df.columns:
                if self._match(n, str(c)):
                    s = pd.to_numeric(df[c], errors="coerce").dropna()
                    if not s.empty:
                        return float(s.iloc[-1])

        # 2. Matrix format (rows have item_id / item / item_en, columns are periods)
        id_cols = [c for c in ["item_id", "item", "item_en"] if c in df.columns]
        if id_cols:
            period_cols, _ = ordered_period_columns(df)   # đúng thứ tự thời gian
            if period_cols:
                for n in names:
                    for _, row in df.iterrows():
                        rks = [str(row[ic]) for ic in id_cols if pd.notna(row[ic])]
                        if any(self._match(n, rk) for rk in rks):
                            vals = pd.to_numeric(row[period_cols], errors="coerce").dropna()
                            # filter out 0 if multiple periods available and earlier has real number
                            non_zero = vals[vals != 0]
                            if not non_zero.empty:
                                return float(non_zero.iloc[-1])
                            elif not vals.empty:
                                return float(vals.iloc[-1])
        return None

    def get_shares_outstanding(self) -> Optional[float]:
        if self.shares and self.shares > 0:
            return self.shares
        shares = self._col(self.ratio_df, ["outstanding_shares", "so cp luu hanh", "shares_outstanding"])
        if shares and shares > 0:
            return shares if shares > 10_000_000 else shares * 1e6
        return None

    # ─────────────────── P/E, P/B, EPS, BVPS ─────────────────────────────────

    def get_pe(self) -> Optional[float]:
        if self.eps_override and self.price > 0:
            return round(self.price / self.eps_override, 2)
        # 1. From ratio df
        pe = self._col(self.ratio_df, ["pe_ratio", "p/e", "pe", "price earning", "price to earnings"])
        if pe is not None and pe > 0:
            return pe
        # 2. Compute from EPS
        eps = self.get_eps()
        if eps and eps > 0 and self.price > 0:
            return round(self.price / eps, 2)
        return None

    def get_pb(self) -> Optional[float]:
        if self.bvps_override and self.price > 0:
            return round(self.price / self.bvps_override, 2)
        # 1. From ratio df
        pb = self._col(self.ratio_df, ["pb_ratio", "p/b", "pb", "price book", "price to book"])
        if pb is not None and pb > 0:
            return pb
        # 2. Compute from BVPS
        bvps = self.get_bvps()
        if bvps and bvps > 0 and self.price > 0:
            return round(self.price / bvps, 2)
        return None

    def get_eps(self) -> Optional[float]:
        if self.eps_override:
            return self.eps_override
        # 1. Direct from ratio df
        eps = self._col(self.ratio_df, ["eps", "earnings per share", "eps_basic_vnd", "lai co ban tren co phieu"])
        if eps is not None and eps > 0:
            return eps

        # 2. Direct from is_df
        eps_is = self._col(self.is_df, ["eps_basic_vnd", "eps", "lai co ban tren co phieu", "net_income_to_common_share"])
        if eps_is is not None and eps_is > 0:
            return eps_is

        # 3. Calculate from price / pe
        pe = self._col(self.ratio_df, ["pe_ratio", "p/e", "pe", "price earning"])
        if pe and pe > 0 and self.price > 0:
            return round(self.price / pe, 1)

        # 4. Calculate from net_profit / shares
        shares = self.get_shares_outstanding()
        net_profit = self._col(self.is_df, [
            "net_profit", "lợi nhuận sau thuế", "net profit", "profit after tax", "loi_nhuan", "LNST", "profit_after_tax"
        ])
        if net_profit and shares and shares > 0 and net_profit > 0:
            return round(net_profit / shares, 1)

        return None

    def get_bvps(self) -> Optional[float]:
        if self.bvps_override:
            return self.bvps_override
        # 1. Direct from ratio df
        bvps = self._col(self.ratio_df, ["bvps", "book value per share", "gia tri so sach"])
        if bvps is not None and bvps > 0:
            return bvps

        # 2. Calculate from price / pb
        pb = self._col(self.ratio_df, ["pb_ratio", "p/b", "pb", "price book"])
        if pb and pb > 0 and self.price > 0:
            return round(self.price / pb, 1)

        # 3. Calculate from balance sheet equity / shares
        shares = self.get_shares_outstanding()
        equity = self._col(self.bs_df, ["owners_equity", "equity", "vốn chủ sở hữu", "von chu so huu"])
        if equity and shares and shares > 0 and equity > 0:
            return round(equity / shares, 1)

        return None

    # ─────────────────── Relative Valuation ──────────────────────────────────

    def relative_valuation(self) -> Dict[str, Any]:
        pe = self.get_pe()
        pb = self.get_pb()
        eps = self.get_eps()
        bvps = self.get_bvps()

        result: Dict[str, Any] = {
            "current_price": self.price,
            "pe": pe,
            "pb": pb,
            "eps": eps,
            "bvps": bvps,
        }

        # Fair value estimates – dùng trung vị P/E, P/B của nhóm ngành khi có
        sector_pe, pe_src = self._sector_multiple("pe", self.MARKET_DEFAULT_PE)
        sector_pb, pb_src = self._sector_multiple("pb", self.MARKET_DEFAULT_PB)
        result["sector_pe"] = sector_pe
        result["sector_pe_source"] = pe_src
        result["sector_pb"] = sector_pb
        result["sector_pb_source"] = pb_src

        estimates = []
        if pe is not None and eps is not None:
            pe_fair = eps * sector_pe
            result["pe_fair_value"] = pe_fair
            result["pe_upside"] = (pe_fair - self.price) / self.price * 100 if self.price else None
            result["pe_vs_sector"] = pe / sector_pe if pe and pe > 0 else None
            estimates.append(pe_fair)

        if pb is not None and bvps is not None:
            pb_fair = bvps * sector_pb
            result["pb_fair_value"] = pb_fair
            result["pb_upside"] = (pb_fair - self.price) / self.price * 100 if self.price else None
            result["pb_vs_sector"] = pb / sector_pb if pb and pb > 0 else None
            estimates.append(pb_fair)

        if estimates:
            result["average_fair_value"] = np.mean(estimates)
            result["upside"] = (result["average_fair_value"] - self.price) / self.price * 100 if self.price else None

        # Valuation assessment
        if pe is not None:
            if pe > THR["pe_overvalued"]:
                result["pe_assessment"] = "Định giá cao"
            elif pe > THR["pe_fair"]:
                result["pe_assessment"] = "Hợp lý"
            elif pe > THR["pe_cheap"]:
                result["pe_assessment"] = "Rẻ hơn thị trường"
            elif pe > 0:
                result["pe_assessment"] = "Rẻ"
            else:
                result["pe_assessment"] = "Lỗ / Không xác định"

        return result

    # ─────────────────── Simplified DCF ──────────────────────────────────────

    def dcf_valuation(
        self,
        growth_rate: float = 0.10,
        terminal_growth: float = 0.04,
        discount_rate: float = 0.12,
        projection_years: int = 5,
    ) -> Dict[str, Any]:
        """
        Simple 2-stage DCF using FCF or EPS as base cash flow.

        Limitations clearly stated in output.
        """
        # Try to find base FCF or EPS
        eps = self.get_eps()
        if eps is None or eps <= 0:
            return {
                "available": False,
                "reason": "EPS âm hoặc không có dữ liệu – không thể DCF",
            }

        # Scenarios
        scenarios = {
            "Thận trọng": (growth_rate * 0.5, terminal_growth * 0.8, discount_rate * 1.1),
            "Cơ sở": (growth_rate, terminal_growth, discount_rate),
            "Lạc quan": (growth_rate * 1.5, terminal_growth * 1.2, discount_rate * 0.9),
        }

        results: Dict[str, float] = {}
        for name, (g, tg, dr) in scenarios.items():
            cf = eps
            pv = 0.0
            for yr in range(1, projection_years + 1):
                cf *= (1 + g)
                pv += cf / (1 + dr) ** yr
            terminal = cf * (1 + tg) / (dr - tg) if dr > tg else cf * 20
            pv += terminal / (1 + dr) ** projection_years
            results[name] = round(pv, 0)

        base_val = results.get("Cơ sở", 0)
        upside = (base_val - self.price) / self.price * 100 if self.price else None

        return {
            "available": True,
            "scenarios": results,
            "current_price": self.price,
            "base_fair_value": base_val,
            "upside_pct": round(upside, 1) if upside is not None else None,
            "assumptions": {
                "growth_rate": f"{growth_rate*100:.0f}%",
                "terminal_growth": f"{terminal_growth*100:.0f}%",
                "discount_rate": f"{discount_rate*100:.0f}%",
                "base": "EPS",
            },
            "limitations": [
                "DCF đơn giản dựa trên EPS hiện tại",
                "Không tính đến thay đổi cơ cấu vốn",
                "Tỷ lệ tăng trưởng là giả định – cần kiểm chứng với dữ liệu lịch sử",
                "Kết quả chỉ mang tính tham khảo",
            ],
        }

    # ─────────────────── Valuation Score ─────────────────────────────────────

    def compute_valuation_score(self) -> Dict[str, Any]:
        """Score valuation 0–100 (higher = more undervalued / reasonable)."""
        rel = self.relative_valuation()
        components: Dict[str, Any] = {}
        missing = []

        # Có dữ liệu ngành -> chấm theo tỷ lệ so với trung vị ngành (định giá TƯƠNG ĐỐI).
        # Không có -> dùng ngưỡng tuyệt đối toàn thị trường và ghi rõ phương pháp.
        has_pe_peer = self.peer_stats.get("pe") is not None
        has_pb_peer = self.peer_stats.get("pb") is not None

        def _rel_score(ratio: float) -> int:
            if ratio < 0.7:
                return 50      # rẻ hơn ngành > 30%
            if ratio <= 1.0:
                return 35      # rẻ hơn hoặc bằng ngành
            if ratio <= 1.3:
                return 20      # đắt hơn ngành ≤ 30%
            return 5           # đắt hơn ngành > 30%

        # ── P/E score (50) ──
        pe = rel.get("pe")
        if pe is not None and pe > 0:
            if has_pe_peer:
                ratio = pe / rel["sector_pe"]
                s = _rel_score(ratio)
                method = f"So với trung vị ngành ({rel['sector_pe']:.1f}x)"
            else:
                ratio = None
                if pe < THR["pe_cheap"]:
                    s = 50
                elif pe <= THR["pe_fair"]:
                    s = 35
                elif pe <= THR["pe_overvalued"]:
                    s = 20
                else:
                    s = 5
                method = "Ngưỡng tuyệt đối thị trường"
            components["pe"] = {"score": s, "max": 50, "value": round(pe, 1),
                                "vs_sector": round(ratio, 2) if ratio else None, "method": method}
        elif pe is not None and pe <= 0:
            components["pe"] = {"score": 0, "max": 50, "value": pe, "note": "Âm"}
        else:
            missing.append("P/E")
            components["pe"] = {"score": None, "max": 50}

        # ── P/B score (50) ──
        pb = rel.get("pb")
        if pb is not None and pb > 0:
            if has_pb_peer:
                ratio = pb / rel["sector_pb"]
                s = _rel_score(ratio)
                method = f"So với trung vị ngành ({rel['sector_pb']:.2f}x)"
            else:
                ratio = None
                if pb < THR["pb_cheap"]:
                    s = 50
                elif pb <= THR["pb_fair"]:
                    s = 35
                elif pb <= THR["pb_overvalued"]:
                    s = 20
                else:
                    s = 5
                method = "Ngưỡng tuyệt đối thị trường"
            components["pb"] = {"score": s, "max": 50, "value": round(pb, 2),
                                "vs_sector": round(ratio, 2) if ratio else None, "method": method}
        else:
            missing.append("P/B")
            components["pb"] = {"score": None, "max": 50}

        available_max = sum(c["max"] for c in components.values() if c.get("score") is not None)
        available_total = sum(c["score"] for c in components.values() if c.get("score") is not None)

        final = round((available_total / available_max) * 100) if available_max > 0 else None

        return {
            "score": final,
            "components": components,
            "missing_data": missing,
            "relative_valuation": rel,
            "dcf": self.dcf_valuation(),
        }
