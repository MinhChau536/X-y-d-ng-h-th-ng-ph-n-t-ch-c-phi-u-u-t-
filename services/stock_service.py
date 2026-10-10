"""
StockService – điều phối dữ liệu & toàn bộ phân tích cho MỘT mã cổ phiếu.

Luồng:
  Giá (DNSE gần nhất + vnstock/Vietstock lịch sử) ─► Kỹ thuật, Động lượng, Rủi ro
  BCTC nhiều nguồn đã chuẩn hóa ─► Bộ tính chỉ số (financial_ratios) ─► Cơ bản, Định giá
  Nhóm ngành ─► Trung vị ngành ─► Định giá tương đối
  Tất cả ─► Điểm cơ hội đầu tư tổng hợp
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, Optional

import pandas as pd

from analytics import financial_ratios as fr
from analytics.fundamental import FundamentalAnalyzer
from analytics.momentum import MomentumAnalyzer
from analytics.opportunity_score import OpportunityScorer
from analytics.peers import compute_peer_stats
from analytics.technical import TechnicalAnalyzer
from analytics.valuation import ValuationEngine
from data.data_repository import DataRepository

logger = logging.getLogger(__name__)
_default_repo: Optional[DataRepository] = None
scorer = OpportunityScorer()


def get_repo() -> DataRepository:
    global _default_repo
    if _default_repo is None:
        _default_repo = DataRepository()
    return _default_repo


class StockService:
    """Full analysis pipeline for a single stock ticker."""

    def __init__(self, symbol: str, days: int = 365, fin_period: str = "year",
                 fin_years: int = 10, repository: Optional[DataRepository] = None):
        self.symbol = symbol.upper().strip()
        self.days = days
        self.fin_period = fin_period
        self.fin_years = fin_years
        self.repo = repository or get_repo()
        self._price_df: Optional[pd.DataFrame] = None
        self._index_df: Optional[pd.DataFrame] = None
        self._company_info: Optional[Dict] = None
        self._peer_stats: Optional[Dict] = None
        self._fin: Dict[str, Dict] = {}
        self._fund_cache: Optional[Dict] = None
        self._summary_cache: Dict[str, Dict] = {}
        self._current: Optional[Dict] = None
        self._errors: Dict[str, str] = {}

    # ─────────────────── Data ────────────────────────────────────────────────

    def get_price_df(self, force_refresh: bool = False) -> pd.DataFrame:
        if self._price_df is None or force_refresh:
            self._price_df = self.repo.get_price_history(self.symbol, days=self.days, force_refresh=force_refresh)
        return self._price_df

    def get_index_df(self) -> pd.DataFrame:
        if self._index_df is None:
            self._index_df = self.repo.get_index_history("VNINDEX", days=self.days)
        return self._index_df

    def get_company_info(self) -> Dict[str, Any]:
        if self._company_info is None:
            self._company_info = self.repo.get_company_info(self.symbol)
        return self._company_info

    def get_current_price(self) -> Optional[Dict[str, Any]]:
        if self._current is None:
            self._current = self.repo.get_current_price(self.symbol)
            if not self._current:
                px = self.get_price_df()
                if not px.empty:
                    self._current = {"symbol": self.symbol, "price": float(px["close"].iloc[-1]),
                                     "timestamp": str(px["timestamp"].iloc[-1]), "source": px["source"].iloc[-1]}
        return self._current

    def _price_vnd(self) -> Optional[float]:
        cur = self.get_current_price()
        return float(cur["price"]) if cur and cur.get("price") else None

    def get_financials(self, period: Optional[str] = None, years: Optional[int] = None) -> Dict[str, Any]:
        period = period or self.fin_period
        key = f"{period}:{years or self.fin_years}"
        if key not in self._fin:
            self._fin[key] = self.repo.get_financials(self.symbol, period=period, years=years or self.fin_years)
        return self._fin[key]

    def financial_summary(self, period: Optional[str] = None) -> Dict[str, Any]:
        """Chỉ số tính từ BCTC + định giá tại giá hiện tại + DuPont + F-score + Z-score."""
        period = period or self.fin_period
        if period not in self._summary_cache:
            data = self.get_financials(period).get("data", pd.DataFrame())
            self._summary_cache[period] = fr.summarize(data, period, self._price_vnd()) if not data.empty \
                else {"period": period, "ratios": pd.DataFrame(), "table": pd.DataFrame(), "valuation": {},
                      "dupont": pd.DataFrame(), "piotroski": None, "altman": {}, "cagr": {}, "is_bank": False}
        return self._summary_cache[period]

    def get_peer_stats(self) -> Dict[str, Any]:
        if self._peer_stats is None:
            try:
                self._peer_stats = compute_peer_stats(self.symbol, self.repo.get_financial_ratios)
            except Exception as exc:
                logger.warning("Peer stats failed for %s: %s", self.symbol, exc)
                self._peer_stats = {"group": None, "n": 0, "reason": str(exc)}
        return self._peer_stats

    # ─────────────────── Technical ───────────────────────────────────────────

    def technical_analysis(self) -> Dict[str, Any]:
        df = self.get_price_df()
        if df.empty:
            return {"available": False, "reason": "Không có dữ liệu giá"}
        ta = TechnicalAnalyzer(df)
        enriched_df = ta.compute_all()
        return {"available": True, "data": enriched_df, "signals": ta.get_signals(),
                "score": ta.compute_technical_score(), "provenance": df.attrs.get("provenance", [])}

    # ─────────────────── Fundamental ─────────────────────────────────────────

    def fundamental_analysis(self) -> Dict[str, Any]:
        if self._fund_cache is not None:
            return self._fund_cache
        fin = self.get_financials()
        canonical = fin.get("data", pd.DataFrame())
        if canonical is not None and not canonical.empty:
            fa = FundamentalAnalyzer(None, None, None, symbol=self.symbol, canonical=canonical, period=self.fin_period)
            raw = fin.get("raw", {})
        else:   # dự phòng: đọc bảng thô theo cách cũ
            is_df = self.repo.get_income_statement(self.symbol)
            bs_df = self.repo.get_balance_sheet(self.symbol)
            cf_df = self.repo.get_cash_flow(self.symbol)
            ratio_df = self.repo.get_financial_ratios(self.symbol)
            fa = FundamentalAnalyzer(is_df, bs_df, cf_df, ratio_df, self.symbol)
            raw = {"income_statement": is_df, "balance_sheet": bs_df, "cash_flow": cf_df, "ratios": ratio_df}
        self._fund_cache = {
            "available": canonical is not None and not canonical.empty,
            "metrics": fa.compute_all(),
            "score": fa.compute_fundamental_score(),
            "raw": raw,
            "sources": fin.get("sources"),
            "attempts": fin.get("attempts", []),
        }
        return self._fund_cache

    # ─────────────────── Momentum ─────────────────────────────────────────────

    def momentum_analysis(self) -> Dict[str, Any]:
        price_df = self.get_price_df()
        ma = MomentumAnalyzer(price_df, self.get_index_df())
        return {"available": not price_df.empty, "score": ma.compute_momentum_score()}

    # ─────────────────── Valuation ────────────────────────────────────────────

    def valuation_analysis(self) -> Dict[str, Any]:
        price = self._price_vnd() or 0
        summ = self.financial_summary()
        val = summ.get("valuation") or {}
        ve = ValuationEngine(self.symbol, price, self.repo.get_financial_ratios(self.symbol),
                             peer_stats=self.get_peer_stats(),
                             eps_override=val.get("eps_ttm"), bvps_override=val.get("bvps"))
        score = ve.compute_valuation_score()
        score["multiples_from_statements"] = {k: val.get(k) for k in ("pe", "pb", "ps", "ev_ebitda", "dividend_yield",
                                                                       "market_cap", "enterprise_value", "as_of_period")}
        return {"available": True, "score": score}

    # ─────────────────── Composite Score ─────────────────────────────────────

    def compute_beta(self, min_obs: int = 60) -> Optional[float]:
        """Beta = Cov(R_cp, R_VNIndex) / Var(R_VNIndex) trên lợi nhuận ngày cùng phiên."""
        try:
            px, idx = self.get_price_df(), self.get_index_df()
            if px.empty or idx.empty:
                return None
            s = px.set_index(pd.to_datetime(px["timestamp"]))["close"].pct_change()
            m = idx.set_index(pd.to_datetime(idx["timestamp"]))["close"].pct_change()
            j = pd.concat([s, m], axis=1, join="inner").dropna()
            if len(j) < min_obs or not j.iloc[:, 1].var():
                return None
            return float(j.iloc[:, 0].cov(j.iloc[:, 1]) / j.iloc[:, 1].var())
        except Exception as exc:
            logger.debug("Beta failed for %s: %s", self.symbol, exc)
            return None

    def compute_opportunity_score(self) -> Dict[str, Any]:
        if not hasattr(self, "_errors"):
            self._errors = {}
        na = {"available": False}
        tech = self._safe("technical", self.technical_analysis, na)
        fund = self._safe("fundamental", self.fundamental_analysis, na)
        mom = self._safe("momentum", self.momentum_analysis, na)
        val = self._safe("valuation", self.valuation_analysis, na)
        pick = lambda sec: sec.get("score", {}).get("score") if sec.get("available") else None  # noqa: E731
        tech_score, fund_score, mom_score, val_score = pick(tech), pick(fund), pick(mom), pick(val)

        price_df = self.get_price_df()
        risk_result: Dict[str, Any] = {"score": None, "components": {}}
        if not price_df.empty:
            daily_ret = price_df["close"].pct_change().dropna()
            vol_30d = float(daily_ret.tail(30).std()) if len(daily_ret) >= 5 else None
            mdd = float(((price_df["close"] - price_df["close"].cummax()) / price_df["close"].cummax()).min())
            de = (fund.get("metrics", {}).get("debt", {}) or {}).get("debt_to_equity")
            risk_result = scorer.compute_risk_score(volatility_30d=vol_30d, max_drawdown=mdd,
                                                    beta=self.compute_beta(), debt_to_equity=de)
        risk_result.setdefault("components", {})
        composite = scorer.compute(tech_score, mom_score, fund_score, val_score, risk_result.get("score"))
        return {"composite": composite,
                "sub_scores": {"technical": tech_score, "momentum": mom_score, "fundamental": fund_score,
                               "valuation": val_score, "risk": risk_result.get("score")},
                "risk_detail": risk_result}

    # ─────────────────── Full Report Data ────────────────────────────────────

    def _safe(self, name: str, fn, default):
        """Chạy một phần phân tích; lỗi ở phần này không làm hỏng các phần khác."""
        try:
            return fn()
        except Exception as exc:
            import traceback
            logger.exception("%s failed for %s", name, self.symbol)
            self._errors[name] = f"{type(exc).__name__}: {exc}\n{traceback.format_exc()}"
            return default

    def full_analysis(self) -> Dict[str, Any]:
        self._errors: Dict[str, str] = {}
        na = lambda reason="Lỗi khi xử lý dữ liệu": {"available": False, "reason": reason}  # noqa: E731
        fin = self._safe("financials", self.get_financials, {})
        return {
            "symbol": self.symbol,
            "timestamp": datetime.now().isoformat(),
            "company_info": self._safe("company_info", self.get_company_info, {}) or {},
            "current_price": self._safe("current_price", self.get_current_price, None),
            "technical": self._safe("technical", self.technical_analysis, na()),
            "fundamental": self._safe("fundamental", self.fundamental_analysis, na()),
            "momentum": self._safe("momentum", self.momentum_analysis, na()),
            "valuation": self._safe("valuation", self.valuation_analysis, na()),
            "opportunity_score": self._safe("opportunity_score", self.compute_opportunity_score,
                                            {"composite": {}, "sub_scores": {}}),
            "peers": self._safe("peers", self.get_peer_stats, {}),
            "financials": {"data": fin.get("data"), "sources": fin.get("sources"),
                           "period": fin.get("period"), "attempts": fin.get("attempts", [])},
            "financial_summary": self._safe("financial_summary", self.financial_summary, {}),
            "index_history": self._safe("index_history", self.get_index_df, None),
            "errors": dict(self._errors),
        }
