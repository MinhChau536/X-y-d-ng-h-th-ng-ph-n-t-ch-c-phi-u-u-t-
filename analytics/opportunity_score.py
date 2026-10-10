"""
Composite Investment Opportunity Score (0–100).

Aggregates technical, momentum, fundamental, valuation, and risk sub-scores.
Weights are configurable. Missing data is explicitly tracked – not set to 0.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from config.constants import DEFAULT_SCORE_WEIGHTS, SCORE_CATEGORIES

logger = logging.getLogger(__name__)


class OpportunityScorer:
    """
    Combine sub-scores into a composite Investment Opportunity Score.

    Score classification (configurable):
      80–100 : Cơ hội nổi bật
      65–79  : Tích cực
      50–64  : Trung tính
      35–49  : Thận trọng
       0–34  : Rủi ro cao

    IMPORTANT: This is a rule-based internal score, NOT a probability of gain.
    """

    def __init__(self, weights: Optional[Dict[str, int]] = None):
        self.weights = weights or DEFAULT_SCORE_WEIGHTS
        # Validate weights sum ≈ 100
        total = sum(self.weights.values())
        if total != 100:
            logger.warning("Score weights sum to %d, not 100. Normalizing.", total)
            self.weights = {k: v / total * 100 for k, v in self.weights.items()}

    def compute(
        self,
        technical_score: Optional[float],
        momentum_score: Optional[float],
        fundamental_score: Optional[float],
        valuation_score: Optional[float],
        risk_score: Optional[float] = None,
        missing_groups: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Aggregate sub-scores into a final composite score.

        Parameters
        ----------
        technical_score    : 0–100 from TechnicalAnalyzer
        momentum_score     : 0–100 from MomentumAnalyzer
        fundamental_score  : 0–100 from FundamentalAnalyzer
        valuation_score    : 0–100 from ValuationEngine
        risk_score         : 0–100 (lower risk = higher risk_score contribution)
        missing_groups     : list of group names with missing data
        """
        scores_input = {
            "technical": technical_score,
            "momentum": momentum_score,
            "fundamental": fundamental_score,
            "valuation": valuation_score,
            "risk": risk_score,
        }

        components: Dict[str, Any] = {}
        weighted_total = 0.0
        available_weight = 0.0

        for group, raw_score in scores_input.items():
            weight = self.weights.get(group, 0)
            if raw_score is None:
                components[group] = {
                    "score": None,
                    "weight": weight,
                    "contribution": None,
                    "status": "missing_data",
                    "reason": f"Không có dữ liệu {group}",
                }
            else:
                capped = max(0.0, min(100.0, float(raw_score)))
                contribution = capped * (weight / 100)
                weighted_total += contribution
                available_weight += weight
                components[group] = {
                    "score": round(capped, 1),
                    "weight": weight,
                    "contribution": round(contribution, 2),
                    "status": "ok",
                }

        # Normalize to available weight
        if available_weight == 0:
            final_score = None
            coverage = 0
            note = "Không đủ dữ liệu để chấm điểm"
        else:
            # Scale score to available weight
            normalized = (weighted_total / available_weight) * 100
            final_score = round(normalized)
            coverage = round(available_weight)
            if coverage < 100:
                note = f"Điểm tính trên {coverage}% trọng số – còn thiếu dữ liệu"
            else:
                note = "Đủ dữ liệu để chấm điểm toàn diện"

        classification = self._classify(final_score)

        return {
            "score": final_score,
            "classification": classification,
            "coverage_pct": coverage,
            "note": note,
            "components": components,
            "disclaimer": (
                "Đây là điểm quy tắc nội bộ, không phải xác suất sinh lời. "
                "Điểm cao không đảm bảo lợi nhuận. Luôn xem xét rủi ro và đa dạng hóa danh mục."
            ),
        }

    @staticmethod
    def _classify(score: Optional[float]) -> Dict[str, str]:
        if score is None:
            return {"label": "Chưa xác định", "color": "#90a4ae", "emoji": "❓"}
        for (lo, hi), (label, color, emoji) in SCORE_CATEGORIES.items():
            if lo <= score <= hi:
                return {"label": label, "color": color, "emoji": emoji}
        return {"label": "Chưa xác định", "color": "#90a4ae", "emoji": "❓"}

    # ─────────────────── Risk Score ───────────────────────────────────────────

    @staticmethod
    def compute_risk_score(
        volatility_30d: Optional[float] = None,
        max_drawdown: Optional[float] = None,
        beta: Optional[float] = None,
        debt_to_equity: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        Compute risk score (0–100, higher = lower risk).

        Chỉ những thành phần CÓ dữ liệu mới được cộng vào mẫu số. Trước đây mẫu số
        luôn là 100 nên khi chỉ có Volatility + Drawdown, điểm tối đa chỉ đạt 60.

        Components:
          Volatility   (30)
          Drawdown     (30)
          Beta         (20)
          Debt/Equity  (20)
        """
        components: Dict[str, Any] = {}
        total = 0.0
        max_pts = 0

        # ── Volatility (30) ──
        if volatility_30d is not None:
            vol_ann = volatility_30d * (252 ** 0.5)
            if vol_ann < 0.2:
                s = 30
            elif vol_ann < 0.35:
                s = 22
            elif vol_ann < 0.5:
                s = 14
            elif vol_ann < 0.7:
                s = 7
            else:
                s = 2
            components["volatility"] = {"score": s, "max": 30, "annualized_vol": round(vol_ann * 100, 1)}
            total += s
            max_pts += 30

        # ── Drawdown (30) ──
        if max_drawdown is not None:
            mdd = abs(max_drawdown)
            if mdd < 0.10:
                s = 30
            elif mdd < 0.20:
                s = 22
            elif mdd < 0.30:
                s = 14
            elif mdd < 0.50:
                s = 7
            else:
                s = 2
            components["drawdown"] = {"score": s, "max": 30, "max_drawdown_pct": round(mdd * 100, 1)}
            total += s
            max_pts += 30

        # ── Beta (20) ──
        if beta is not None:
            if 0.5 <= beta <= 1.2:
                s = 20
            elif beta < 0.5:
                s = 15
            elif beta <= 1.5:
                s = 12
            else:
                s = 5
            components["beta"] = {"score": s, "max": 20, "value": round(beta, 2)}
            total += s
            max_pts += 20

        # ── Debt (20) ──
        if debt_to_equity is not None:
            if debt_to_equity <= 0.5:
                s = 20
            elif debt_to_equity <= 1.0:
                s = 14
            elif debt_to_equity <= 2.0:
                s = 7
            else:
                s = 2
            components["debt_equity"] = {"score": s, "max": 20, "value": round(debt_to_equity, 2)}
            total += s
            max_pts += 20

        if max_pts == 0:
            return {
                "score": None,
                "components": components,
                "coverage_pts": 0,
                "interpretation": "Không đủ dữ liệu",
            }
        final = round((total / max_pts) * 100)

        return {
            "score": final,
            "components": components,
            "coverage_pts": max_pts,
            "interpretation": "Rủi ro thấp" if final >= 70 else "Rủi ro trung bình" if final >= 50 else "Rủi ro cao",
        }

    @staticmethod
    def compute_market_health_score(
        advance_decline: Optional[float] = None,
        index_above_ma: Optional[bool] = None,
        avg_rsi: Optional[float] = None,
        foreign_net_buy: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        Market Health Score 0–100.

        Components:
          Advance/Decline ratio (30)
          Index above SMA50     (25)
          Market avg RSI        (25)
          Foreign net buying    (20)
        """
        components: Dict[str, Any] = {}
        total = 0.0
        max_pts = 0

        # Advance/Decline (30)
        if advance_decline is not None:
            max_pts += 30
            if advance_decline > 2.0:
                s = 30
            elif advance_decline > 1.5:
                s = 22
            elif advance_decline > 1.0:
                s = 15
            elif advance_decline > 0.5:
                s = 8
            else:
                s = 2
            components["advance_decline"] = {"score": s, "max": 30, "ratio": round(advance_decline, 2)}
            total += s

        # Index above MA (25)
        if index_above_ma is not None:
            max_pts += 25
            s = 25 if index_above_ma else 5
            components["index_ma"] = {"score": s, "max": 25, "above_ma50": index_above_ma}
            total += s

        # Market RSI (25)
        if avg_rsi is not None:
            max_pts += 25
            if 50 <= avg_rsi <= 65:
                s = 25
            elif 40 <= avg_rsi < 50:
                s = 15
            elif avg_rsi > 65:
                s = 10
            else:
                s = 5
            components["market_rsi"] = {"score": s, "max": 25, "value": round(avg_rsi, 1)}
            total += s

        # Foreign (20)
        if foreign_net_buy is not None:
            max_pts += 20
            if foreign_net_buy > 0:
                s = 20
            elif foreign_net_buy > -100e9:
                s = 10
            else:
                s = 3
            components["foreign"] = {"score": s, "max": 20, "net_buy": foreign_net_buy}
            total += s

        # Chỉ chia cho tổng điểm của các thành phần có dữ liệu
        final = round((total / max_pts) * 100) if max_pts else None
        return {"score": final, "components": components}
