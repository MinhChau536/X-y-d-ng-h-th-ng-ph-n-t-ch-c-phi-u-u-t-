"""
Danh mục theo dõi (watchlist) & cảnh báo giá.

Điều kiện cảnh báo:
  price_above / price_below   : giá hiện tại ≥ / ≤ ngưỡng (VND)
  change_above / change_below : % thay đổi trong phiên ≥ / ≤ ngưỡng
  rsi_above / rsi_below       : RSI(14) ≥ / ≤ ngưỡng
Cảnh báo được kiểm tra mỗi lần mở trang Danh mục theo dõi và bởi script cập nhật hằng ngày;
khi kích hoạt, cảnh báo chuyển sang trạng thái đã kích hoạt kèm thời điểm và giá.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

import pandas as pd

from analytics.indicators import rsi_wilder
from data.database import Database

CONDITIONS = {
    "price_above": "Giá ≥ ngưỡng (VND)",
    "price_below": "Giá ≤ ngưỡng (VND)",
    "change_above": "Tăng trong phiên ≥ (%)",
    "change_below": "Giảm trong phiên ≤ (%)",
    "rsi_above": "RSI(14) ≥",
    "rsi_below": "RSI(14) ≤",
}


def check_condition(condition: str, threshold: float, price: Optional[float],
                    change_pct: Optional[float], rsi: Optional[float]) -> Optional[bool]:
    """True/False nếu đủ dữ liệu để kiểm tra, None nếu thiếu dữ liệu."""
    val = {"price": price, "change": change_pct, "rsi": rsi}[condition.split("_")[0]]
    if val is None or pd.isna(val):
        return None
    return val >= threshold if condition.endswith("above") else val <= threshold


class WatchlistService:

    def __init__(self, repo=None, db: Optional[Database] = None):
        if repo is None:
            from services.stock_service import get_repo
            repo = get_repo()
        self.repo = repo
        self.db = db or Database()

    # ── Watchlist ──
    def add(self, symbol: str, note: str = ""):
        self.db.add_watch(symbol, note)

    def remove(self, symbol: str):
        self.db.remove_watch(symbol)

    def symbols(self) -> List[str]:
        df = self.db.get_watchlist()
        return df["symbol"].tolist() if not df.empty else []

    def snapshot(self) -> pd.DataFrame:
        """Giá, % thay đổi phiên, % 1 tháng, RSI cho từng mã đang theo dõi."""
        rows = []
        for sym in self.symbols():
            rows.append(self._quote(sym))
        return pd.DataFrame(rows)

    def _quote(self, sym: str) -> Dict[str, Any]:
        cur = self.repo.get_current_price(sym) or {}
        px = self.repo.get_price_history(sym, days=60)
        rsi = None
        chg_1m = None
        if px is not None and not px.empty:
            r = rsi_wilder(px["close"], 14).dropna()
            rsi = float(r.iloc[-1]) if not r.empty else None
            if len(px) > 21:
                chg_1m = (float(px["close"].iloc[-1]) / float(px["close"].iloc[-22]) - 1) * 100
        price = cur.get("price") or (float(px["close"].iloc[-1]) if px is not None and not px.empty else None)
        chg = cur.get("change_pct")
        if chg is None and px is not None and len(px) > 1:
            chg = (float(px["close"].iloc[-1]) / float(px["close"].iloc[-2]) - 1) * 100
        return {"symbol": sym, "price": price, "change_pct": chg, "change_1m_pct": chg_1m, "rsi": rsi,
                "source": cur.get("source") or (px["source"].iloc[-1] if px is not None and not px.empty else None)}

    # ── Alerts ──
    def add_alert(self, symbol: str, condition: str, threshold: float):
        if condition not in CONDITIONS:
            raise ValueError(condition)
        self.db.add_alert(symbol, condition, threshold)

    def alerts(self, active_only: bool = False) -> pd.DataFrame:
        df = self.db.get_alerts(active_only)
        if not df.empty:
            df["condition_label"] = df["condition"].map(CONDITIONS)
        return df

    def delete_alert(self, alert_id: int):
        self.db.delete_alert(alert_id)

    def evaluate(self) -> List[Dict[str, Any]]:
        """Kiểm tra mọi cảnh báo đang bật; trả về danh sách cảnh báo vừa kích hoạt."""
        active = self.db.get_alerts(active_only=True)
        if active.empty:
            return []
        triggered = []
        quotes: Dict[str, Dict[str, Any]] = {}
        for _, a in active.iterrows():
            q = quotes.setdefault(a["symbol"], self._quote(a["symbol"]))
            hit = check_condition(a["condition"], float(a["threshold"]), q["price"], q["change_pct"], q["rsi"])
            if hit:
                self.db.mark_alert_triggered(int(a["id"]), float(q["price"] or 0))
                triggered.append({"id": int(a["id"]), "symbol": a["symbol"], "condition": CONDITIONS[a["condition"]],
                                  "threshold": float(a["threshold"]), "price": q["price"],
                                  "change_pct": q["change_pct"], "rsi": q["rsi"]})
        return triggered
