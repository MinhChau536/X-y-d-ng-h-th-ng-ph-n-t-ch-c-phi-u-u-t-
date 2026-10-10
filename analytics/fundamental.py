"""
Fundamental Analysis engine.

Analyzes financial statements (IS, BS, CF) and computes:
- Revenue / profit trends
- Profitability ratios (ROE, ROA, margins)
- Debt structure
- Cash flow quality
- Earnings quality warnings
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from analytics.period_utils import (
    flatten_columns, growth_vs_prior, key_to_label, order_tabular, ordered_period_columns,
)
from config.constants import FUNDAMENTAL_THRESHOLDS as THR

logger = logging.getLogger(__name__)


def _safe_float(val) -> Optional[float]:
    try:
        if pd.isna(val):
            return None
        return float(val)
    except (TypeError, ValueError):
        return None


def _pct_change(new: Optional[float], old: Optional[float]) -> Optional[float]:
    if new is None or old is None or old == 0:
        return None
    return (new - old) / abs(old) * 100


class FundamentalAnalyzer:
    """
    Compute fundamental metrics from financial statement DataFrames.

    Parameters
    ----------
    is_df : Income Statement (quarterly preferred)
    bs_df : Balance Sheet
    cf_df : Cash Flow
    ratio_df : Pre-computed ratios from provider
    symbol : Ticker
    """

    def __init__(
        self,
        is_df: pd.DataFrame,
        bs_df: pd.DataFrame,
        cf_df: pd.DataFrame,
        ratio_df: pd.DataFrame = None,
        symbol: str = "",
        canonical: Optional[pd.DataFrame] = None,
        period: str = "year",
    ):
        """
        canonical: bảng BCTC đã chuẩn hóa (DataRepository.get_financials()["data"]).
                   Khi có, mọi chỉ số được TÍNH TỪ BCTC bằng analytics.financial_ratios
                   thay vì đọc bảng chỉ số dựng sẵn của nhà cung cấp.
        """
        self.canonical = canonical if canonical is not None and not canonical.empty else None
        self.period = period
        # Chuẩn hóa cột (gộp MultiIndex) và SẮP XẾP KỲ tăng dần theo thời gian,
        # để .iloc[-1] luôn là kỳ mới nhất và có thể so sánh đúng cùng kỳ năm trước.
        self.is_df = order_tabular(flatten_columns(is_df))
        self.bs_df = order_tabular(flatten_columns(bs_df))
        self.cf_df = order_tabular(flatten_columns(cf_df))
        self.ratio_df = order_tabular(flatten_columns(ratio_df))
        self.symbol = symbol
        self._metrics: Dict[str, Any] = {}

    # ─────────────────── Column helpers ──────────────────────────────────────

    def _find_col(self, df: pd.DataFrame, candidates: List[str]) -> Optional[str]:
        """Return first matching column name (case-insensitive)."""
        if df is None or df.empty:
            return None
        for c in candidates:
            for col in df.columns:
                col = str(col)
                if col.lower() == c.lower() or c.lower() in col.lower():
                    return col
        return None

    def _series(self, df: pd.DataFrame, candidates: List[str]) -> pd.Series:
        if df is None or df.empty:
            return pd.Series(dtype=float)

        # 1. Check matching column name (tabular format)
        col = self._find_col(df, candidates)
        if col and col in df.columns:
            s = pd.to_numeric(df[col], errors="coerce")
            if s.notna().any():
                return s

        # 2. Check matrix format (rows are item_id / item, columns are periods)
        id_cols = [c for c in ["item_id", "item", "item_en"] if c in df.columns]
        if id_cols:
            # Cột kỳ được sắp theo đúng thứ tự thời gian (không phải sort chữ cái)
            period_cols, period_keys = ordered_period_columns(df)
            if period_cols:
                for c in candidates:
                    c_clean = c.lower().replace("_", "").replace(" ", "").replace("/", "").replace("%", "")
                    for _, row in df.iterrows():
                        rks = [str(row[ic]).lower() for ic in id_cols if pd.notna(row[ic])]
                        matched = any(
                            c_clean == rk.replace("_", "").replace(" ", "").replace("/", "").replace("%", "")
                            or c_clean in rk.replace("_", "").replace(" ", "").replace("/", "").replace("%", "")
                            or rk.replace("_", "").replace(" ", "").replace("/", "").replace("%", "") in c_clean
                            for rk in rks
                        )
                        if matched:
                            vals = pd.to_numeric(row[period_cols], errors="coerce")
                            if all(k is not None for k in period_keys):
                                vals.index = period_keys
                            vals = vals.dropna()
                            if not vals.empty:
                                return vals

        return pd.Series(dtype=float)

    # ─────────────────── Revenue & Profit ────────────────────────────────────

    def get_revenue_profit_trend(self) -> Dict[str, Any]:
        if self.is_df.empty:
            return {"available": False, "reason": "Không có dữ liệu KQKD"}

        # Try common Vietnamese and English column names
        revenue = self._series(self.is_df, [
            "doanh thu", "revenue", "net revenue", "doanh_thu", "doanh thu thuần", "operating_sales", "net_sales"
        ])
        net_profit = self._series(self.is_df, [
            "lợi nhuận sau thuế", "net profit", "profit after tax", "loi_nhuan", "LNST", "net_profit", "profit_after_tax"
        ])
        gross_profit = self._series(self.is_df, [
            "lợi nhuận gộp", "gross profit", "loi nhuan gop", "gross_profit"
        ])

        result: Dict[str, Any] = {"available": True}

        if not revenue.empty and revenue.notna().any():
            rev = revenue.dropna()
            g = growth_vs_prior(rev)
            result["revenue_latest"] = float(rev.iloc[-1])
            result["revenue_prev"] = float(rev.iloc[-2]) if len(rev) > 1 else None
            # revenue_yoy = tăng trưởng so với CÙNG KỲ năm trước khi xác định được kỳ
            result["revenue_yoy"] = g["pct"]
            result["revenue_growth_basis"] = g["basis"]
            result["latest_period"] = g["latest_period"]
            result["compare_period"] = g["compare_period"]
            result["revenue_series"] = rev.values.tolist()
            result["periods"] = [key_to_label(k) for k in rev.index]

        if not net_profit.empty and net_profit.notna().any():
            npf = net_profit.dropna()
            g = growth_vs_prior(npf)
            result["net_profit_latest"] = float(npf.iloc[-1])
            result["net_profit_prev"] = float(npf.iloc[-2]) if len(npf) > 1 else None
            result["net_profit_yoy"] = g["pct"]
            result["net_profit_growth_basis"] = g["basis"]
            result["net_profit_series"] = npf.values.tolist()
            result["net_profit_periods"] = [key_to_label(k) for k in npf.index]

        # Margin
        rev_l = result.get("revenue_latest")
        np_l = result.get("net_profit_latest")
        gp_vals = gross_profit.dropna().values if not gross_profit.empty else []
        gp_l = float(gp_vals[-1]) if len(gp_vals) else None

        if rev_l and rev_l != 0:
            if np_l is not None:
                result["net_margin"] = np_l / rev_l * 100
            if gp_l is not None:
                result["gross_margin"] = gp_l / rev_l * 100

        # Quality warning: revenue up but profit down
        result["warnings"] = []
        rev_yoy = result.get("revenue_yoy")
        np_yoy = result.get("net_profit_yoy")
        if rev_yoy is not None and np_yoy is not None:
            if rev_yoy > 5 and np_yoy < -5:
                result["warnings"].append("Doanh thu tăng nhưng lợi nhuận giảm – cần kiểm tra chi phí")

        return result

    # ─────────────────── ROE / ROA ────────────────────────────────────────────

    def get_return_metrics(self) -> Dict[str, Any]:
        result: Dict[str, Any] = {}

        # From ratio df if available
        if not self.ratio_df.empty:
            roe = self._series(self.ratio_df, ["roe", "return on equity"])
            roa = self._series(self.ratio_df, ["roa", "return on assets"])
            if not roe.empty and roe.notna().any():
                v = float(roe.dropna().iloc[-1])
                result["roe"] = v * 100 if abs(v) < 1.0 else v
            if not roa.empty and roa.notna().any():
                v = float(roa.dropna().iloc[-1])
                result["roa"] = v * 100 if abs(v) < 1.0 else v

        # Compute from IS + BS if not available from ratios
        if "roe" not in result and not self.is_df.empty and not self.bs_df.empty:
            np_series = self._series(self.is_df, ["lợi nhuận sau thuế", "net profit", "LNST", "net_profit", "profit_after_tax"])
            equity_series = self._series(self.bs_df, ["vốn chủ sở hữu", "equity", "total equity", "owners_equity"])
            if np_series.notna().any() and equity_series.notna().any():
                np_val = float(np_series.dropna().iloc[-1])
                eq_val = float(equity_series.dropna().iloc[-1])
                if eq_val != 0:
                    result["roe"] = np_val / eq_val * 100

        if "roa" not in result and not self.is_df.empty and not self.bs_df.empty:
            np_series = self._series(self.is_df, ["lợi nhuận sau thuế", "net profit", "LNST", "net_profit", "profit_after_tax"])
            asset_series = self._series(self.bs_df, ["tổng tài sản", "total assets", "total_assets"])
            if np_series.notna().any() and asset_series.notna().any():
                np_val = float(np_series.dropna().iloc[-1])
                ta_val = float(asset_series.dropna().iloc[-1])
                if ta_val != 0:
                    result["roa"] = np_val / ta_val * 100

        return result

    # ─────────────────── Debt ────────────────────────────────────────────────

    def get_debt_metrics(self) -> Dict[str, Any]:
        if self.bs_df.empty and self.ratio_df.empty:
            return {"available": False}

        result: Dict[str, Any] = {"available": True}
        total_debt = self._series(self.bs_df, ["tổng nợ", "total debt", "total liabilities", "nợ phải trả", "liabilities"])
        equity = self._series(self.bs_df, ["vốn chủ sở hữu", "equity", "total equity", "owners_equity"])
        total_assets = self._series(self.bs_df, ["tổng tài sản", "total assets", "total_assets"])

        if not total_debt.empty and total_debt.notna().any():
            result["total_debt"] = float(total_debt.dropna().iloc[-1])
        if not equity.empty and equity.notna().any():
            eq = float(equity.dropna().iloc[-1])
            result["equity"] = eq
            td = result.get("total_debt")
            if td is not None and eq != 0:
                result["debt_to_equity"] = td / eq

        if not total_assets.empty and total_assets.notna().any():
            ta = float(total_assets.dropna().iloc[-1])
            result["total_assets"] = ta
            td = result.get("total_debt")
            if td is not None and ta != 0:
                result["debt_to_assets"] = td / ta

        # Also fallback to pre-calculated ratio from ratio_df
        if "debt_to_equity" not in result and not self.ratio_df.empty:
            de_r = self._series(self.ratio_df, ["debt_to_equity", "debtPerEquity", "nợ/vốn chủ", "nợ trên vốn chủ"])
            if not de_r.empty and de_r.notna().any():
                result["debt_to_equity"] = float(de_r.dropna().iloc[-1])

        # Warning
        result["warnings"] = []
        de = result.get("debt_to_equity")
        if de is not None and de > THR["debt_equity_high"]:
            result["warnings"].append(f"Tỷ lệ Nợ/VCSH cao: {de:.2f}x")

        return result

    # ─────────────────── Cash Flow ────────────────────────────────────────────

    def get_cashflow_metrics(self) -> Dict[str, Any]:
        if self.cf_df.empty:
            return {"available": False}

        result: Dict[str, Any] = {"available": True}
        cfo = self._series(self.cf_df, [
            "tiền từ hoạt động kinh doanh", "operating cash flow", "CFO", "cash from operations", "operating_cash_flows", "hoạt động kinh doanh"
        ])
        capex = self._series(self.cf_df, [
            "mua tài sản cố định", "capex", "capital expenditure", "purchase_of_fixed_assets", "tiền chi để mua sắm"
        ])

        if not cfo.empty and cfo.notna().any():
            result["cfo_latest"] = float(cfo.dropna().iloc[-1])
            result["cfo_series"] = cfo.dropna().tolist()

        if not capex.empty and capex.notna().any():
            cap = float(capex.dropna().iloc[-1])
            result["capex_latest"] = cap
            cfo_l = result.get("cfo_latest")
            if cfo_l is not None:
                result["fcf"] = cfo_l + cap  # capex usually negative in CF

        result["warnings"] = []
        cfo_l = result.get("cfo_latest")
        np_ref = None  # Would need IS data
        if cfo_l is not None and cfo_l < 0:
            result["warnings"].append("Dòng tiền hoạt động âm – cần chú ý")

        return result

    # ─────────────────── Full metrics ────────────────────────────────────────

    # ─────────────────── Canonical path (tính từ BCTC) ───────────────────────

    def _compute_all_canonical(self) -> Dict[str, Any]:
        from analytics.financial_ratios import compute_ratios
        w = self.canonical.sort_index()
        ratios = compute_ratios(w, self.period)
        last = ratios.iloc[-1] if not ratios.empty else pd.Series(dtype=float)
        val = lambda s, k: (float(s[k]) if k in s.index and pd.notna(s[k]) else None)  # noqa: E731
        rp: Dict[str, Any] = {"available": True, "warnings": []}
        rev_col = "revenue" if "revenue" in w.columns else ("total_operating_income" if "total_operating_income" in w.columns else None)
        if rev_col:
            rev = w[rev_col].dropna()
            g = growth_vs_prior(rev)
            rp.update({"revenue_latest": float(rev.iloc[-1]) if len(rev) else None,
                       "revenue_yoy": g["pct"], "revenue_growth_basis": g["basis"],
                       "latest_period": g["latest_period"], "compare_period": g["compare_period"],
                       "revenue_series": rev.values.tolist(), "periods": [key_to_label(k) for k in rev.index]})
        ni_col = "net_income_parent" if "net_income_parent" in w.columns else ("net_income" if "net_income" in w.columns else None)
        if ni_col:
            npf = w[ni_col].dropna()
            g = growth_vs_prior(npf)
            rp.update({"net_profit_latest": float(npf.iloc[-1]) if len(npf) else None,
                       "net_profit_yoy": g["pct"], "net_profit_growth_basis": g["basis"],
                       "net_profit_series": npf.values.tolist(),
                       "net_profit_periods": [key_to_label(k) for k in npf.index]})
        rp["net_margin"] = val(last, "net_margin")
        rp["gross_margin"] = val(last, "gross_margin")
        if rp.get("revenue_yoy") is not None and rp.get("net_profit_yoy") is not None \
                and rp["revenue_yoy"] > 5 and rp["net_profit_yoy"] < -5:
            rp["warnings"].append("Doanh thu tăng nhưng lợi nhuận giảm – cần kiểm tra chi phí")
        de = val(last, "debt_to_equity")
        if de is None:
            de = val(last, "liabilities_to_equity")
        debt = {"available": True, "debt_to_equity": de,
                "liabilities_to_equity": val(last, "liabilities_to_equity"),
                "debt_to_assets": (val(last, "liabilities_to_assets") or 0) / 100 if val(last, "liabilities_to_assets") is not None else None,
                "warnings": []}
        if de is not None and de > THR["debt_equity_high"]:
            debt["warnings"].append(f"Tỷ lệ Nợ/VCSH cao: {de:.2f}x")
        cfo = w["cfo"].dropna() if "cfo" in w.columns else pd.Series(dtype=float)
        cf = {"available": not cfo.empty, "cfo_latest": float(cfo.iloc[-1]) if not cfo.empty else None,
              "fcf": val(last, "fcf"), "cfo_series": cfo.tolist(), "warnings": []}
        if cf["cfo_latest"] is not None and cf["cfo_latest"] < 0:
            cf["warnings"].append("Dòng tiền hoạt động âm – cần chú ý")
        return {
            "revenue_profit": rp,
            "return_metrics": {"roe": val(last, "roe"), "roa": val(last, "roa"), "roic": val(last, "roic")},
            "debt": debt,
            "cashflow": cf,
            "ratios": ratios,
            "symbol": self.symbol,
            "basis": "Tính từ BCTC chuẩn hóa" + (" (TTM)" if self.period == "quarter" else ""),
        }

    def compute_all(self) -> Dict[str, Any]:
        if self.canonical is not None:
            return self._compute_all_canonical()
        return {
            "revenue_profit": self.get_revenue_profit_trend(),
            "return_metrics": self.get_return_metrics(),
            "debt": self.get_debt_metrics(),
            "cashflow": self.get_cashflow_metrics(),
            "symbol": self.symbol,
        }

    # ─────────────────── Fundamental Score ───────────────────────────────────

    def compute_fundamental_score(self) -> Dict[str, Any]:
        """
        Score fundamental quality 0–100.

        Components:
          ROE (25), Revenue growth (20), Margin (20), Debt (20), CFO quality (15)
        """
        metrics = self.compute_all()
        components: Dict[str, Any] = {}
        total = 0.0
        max_pts = 0
        missing = []

        # ── ROE (25) ──
        max_pts += 25
        rm = metrics.get("return_metrics", {})
        roe = rm.get("roe")
        if roe is not None:
            if roe >= THR["roe_excellent"]:
                s = 25
            elif roe >= THR["roe_good"]:
                s = 18
            elif roe >= THR["roe_fair"]:
                s = 12
            elif roe >= 0:
                s = 5
            else:
                s = 0
            components["roe"] = {"score": s, "max": 25, "value": round(roe, 2)}
            total += s
        else:
            missing.append("ROE")
            components["roe"] = {"score": None, "max": 25, "reason": "Không có dữ liệu"}

        # ── Revenue Growth (20) ──
        max_pts += 20
        rp = metrics.get("revenue_profit", {})
        rev_yoy = rp.get("revenue_yoy")
        if rev_yoy is not None:
            if rev_yoy >= 20:
                s = 20
            elif rev_yoy >= 10:
                s = 15
            elif rev_yoy >= 0:
                s = 10
            elif rev_yoy >= -10:
                s = 5
            else:
                s = 0
            components["revenue_growth"] = {
                "score": s, "max": 20, "value": round(rev_yoy, 1),
                "basis": rp.get("revenue_growth_basis"),
            }
            total += s
        else:
            missing.append("Tăng trưởng DT")
            components["revenue_growth"] = {"score": None, "max": 20}

        # ── Net Margin (20) ──
        max_pts += 20
        margin = rp.get("net_margin")
        if margin is not None:
            if margin >= THR["net_margin_excellent"]:
                s = 20
            elif margin >= THR["net_margin_good"]:
                s = 14
            elif margin >= THR["net_margin_fair"]:
                s = 8
            elif margin >= 0:
                s = 3
            else:
                s = 0
            components["margin"] = {"score": s, "max": 20, "value": round(margin, 2)}
            total += s
        else:
            missing.append("Biên lợi nhuận")
            components["margin"] = {"score": None, "max": 20}

        # ── Debt (20) ──
        max_pts += 20
        debt = metrics.get("debt", {})
        de = debt.get("debt_to_equity")
        if de is not None:
            if de <= 0.5:
                s = 20
            elif de <= 1.0:
                s = 15
            elif de <= 1.5:
                s = 10
            elif de <= THR["debt_equity_high"]:
                s = 5
            else:
                s = 0
            components["debt"] = {"score": s, "max": 20, "value": round(de, 2)}
            total += s
        else:
            missing.append("Cơ cấu nợ")
            components["debt"] = {"score": None, "max": 20}

        # ── CFO quality (15) ──
        max_pts += 15
        cf = metrics.get("cashflow", {})
        cfo = cf.get("cfo_latest")
        np_l = rp.get("net_profit_latest")
        if cfo is not None:
            if cfo > 0:
                if np_l and np_l > 0:
                    # CFO/NP ratio > 1 is ideal
                    ratio = cfo / np_l
                    if ratio >= 1.0:
                        s = 15
                    elif ratio >= 0.5:
                        s = 10
                    else:
                        s = 5
                else:
                    s = 8
            else:
                s = 0
            components["cashflow"] = {"score": s, "max": 15, "cfo": cfo}
            total += s
        else:
            missing.append("Dòng tiền")
            components["cashflow"] = {"score": None, "max": 15}

        # Compute score only on available data
        available_max = sum(
            c["max"] for c in components.values() if c.get("score") is not None
        )
        available_total = sum(
            c["score"] for c in components.values() if c.get("score") is not None
        )

        if available_max == 0:
            final_score = None
            note = "Không đủ dữ liệu để chấm điểm"
        else:
            final_score = round((available_total / available_max) * 100)
            note = f"Tính trên {len(components) - len(missing)}/{len(components)} nhóm chỉ tiêu"

        return {
            "score": final_score,
            "note": note,
            "components": components,
            "missing_data": missing,
        }
