"""
MarketService – provides market-level overview and index data.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import pandas as pd

from services.stock_service import get_repo

logger = logging.getLogger(__name__)


INDEX_SYMBOLS = {
    "VNINDEX": "VN-Index",
    "VN30": "VN30",
    "HNX": "HNX-Index",
    "UPCOM": "UPCoM-Index",
}


class MarketService:
    """Market overview data and health scoring."""

    def get_index_snapshots(self) -> Dict[str, Any]:
        """Return current snapshot for main indices."""
        result = {}
        for code, name in INDEX_SYMBOLS.items():
            try:
                # Look back up to 14 days to handle holidays / weekends safely
                end = datetime.now().strftime("%Y-%m-%d")
                start = (datetime.now() - timedelta(days=14)).strftime("%Y-%m-%d")

                candidates = [code]
                if code == "HNX":
                    candidates = ["HNX", "HNXINDEX", "HNXIndex"]
                elif code == "UPCOM":
                    candidates = ["UPCOM", "UPCOMINDEX", "UpcomIndex"]

                df = pd.DataFrame()
                for sym in candidates:
                    try:
                        df = get_repo().get_price_history(sym, start_date=start, end_date=end)
                        if not df.empty:
                            break
                    except Exception:
                        continue

                if not df.empty:
                    last = df.iloc[-1]
                    prev = df.iloc[-2] if len(df) > 1 else last
                    close = float(last.get("close", 0))
                    prev_close = float(prev.get("close", close))
                    change = close - prev_close
                    change_pct = change / prev_close * 100 if prev_close else 0
                    result[code] = {
                        "name": name,
                        "close": close,
                        "change": round(change, 2),
                        "change_pct": round(change_pct, 2),
                        "volume": float(last.get("volume", 0)),
                        "date": str(last.get("timestamp", ""))[:10],
                        "available": True,
                    }
                else:
                    result[code] = {"name": name, "available": False}
            except Exception as exc:
                logger.warning("Index snapshot failed for %s: %s", code, exc)
                result[code] = {"name": name, "available": False, "error": str(exc)}
        return result

    def get_index_history(self, index_code: str = "VNINDEX", days: int = 365) -> pd.DataFrame:
        return get_repo().get_index_history(index_code, days=days)

    def get_market_breadth(self, df: pd.DataFrame) -> Dict[str, Any]:
        """
        Compute market breadth from a board/listing DataFrame.

        Expected columns: symbol, change or change_pct
        """
        if df.empty:
            return {"available": False}

        change_col = None
        for c in ["change", "change_pct", "priceChange", "percentChange"]:
            if c in df.columns:
                change_col = c
                break

        if change_col is None:
            return {"available": False, "reason": "Không có cột thay đổi giá"}

        changes = pd.to_numeric(df[change_col], errors="coerce").dropna()
        advancing = int((changes > 0).sum())
        declining = int((changes < 0).sum())
        unchanged = int((changes == 0).sum())
        total = advancing + declining + unchanged
        ad_ratio = advancing / declining if declining > 0 else float("inf")

        return {
            "available": True,
            "advancing": advancing,
            "declining": declining,
            "unchanged": unchanged,
            "total": total,
            "ad_ratio": round(ad_ratio, 2),
        }

    def get_top_movers(self, df: pd.DataFrame, n: int = 10) -> Dict[str, pd.DataFrame]:
        """Return top gainers, losers, and highest volume."""
        result = {"gainers": pd.DataFrame(), "losers": pd.DataFrame(), "volume": pd.DataFrame()}
        if df.empty:
            return result

        change_col = next((c for c in ["change_pct", "percentChange", "change"] if c in df.columns), None)
        vol_col = next((c for c in ["volume", "totalVolume", "tradingVolume"] if c in df.columns), None)
        sym_col = next((c for c in ["symbol", "ticker", "code"] if c in df.columns), None)

        if change_col and sym_col:
            df2 = df.copy()
            df2[change_col] = pd.to_numeric(df2[change_col], errors="coerce")
            result["gainers"] = df2.nlargest(n, change_col)
            result["losers"] = df2.nsmallest(n, change_col)

        if vol_col and sym_col:
            df2 = df.copy()
            df2[vol_col] = pd.to_numeric(df2[vol_col], errors="coerce")
            result["volume"] = df2.nlargest(n, vol_col)

        return result

    def get_provider_status(self) -> Dict[str, Any]:
        return get_repo().get_provider_status()


# ═════════════════════════════════════════════════════════════════════════════
#  Bộ tính toán cho trang Tổng quan thị trường (chỉ dùng dữ liệu giá thật)
# ═════════════════════════════════════════════════════════════════════════════
import math
from concurrent.futures import ThreadPoolExecutor

import numpy as np

_INDEX_CANDIDATES = {
    "VNINDEX": ["VNINDEX"],
    "VN30": ["VN30"],
    "HNX": ["HNX", "HNXINDEX", "HNXIndex"],
    "UPCOM": ["UPCOM", "UPCOMINDEX", "UpcomIndex"],
}

# Ngành cho các mã VN30 không nằm trong rổ ngành của ticker_directory
_SECTOR_OVERRIDE = {"BVH": "🛡️ Bảo hiểm", "VJC": "✈️ Hàng không", "BCM": "🏢 Bất động sản"}


def sector_map() -> Dict[str, str]:
    """Mã → ngành, lấy từ các rổ ngành trong ticker_directory (bỏ rổ chỉ số)."""
    from data.ticker_directory import BASKETS
    out: Dict[str, str] = {}
    for name, syms in BASKETS.items():
        if not syms or "⭐" in name or name.startswith("Tất cả"):
            continue
        for s in syms:
            out.setdefault(s, name)
    out.update(_SECTOR_OVERRIDE)
    return out


def universe_options() -> Dict[str, List[str]]:
    """Các rổ cổ phiếu dùng để đo độ rộng / heatmap."""
    from data.ticker_directory import BASKETS
    opts: Dict[str, List[str]] = {}
    for name, syms in BASKETS.items():
        if syms:
            opts[name] = list(dict.fromkeys(syms))
    sector_all: List[str] = []
    for name, syms in BASKETS.items():
        if syms and "⭐" not in name:
            sector_all += syms
    opts = {"⭐ VN30 (Blue-chips HSX)": opts.pop("⭐ VN30 (Blue-chips HSX)"),
            "🌐 Rổ mở rộng (VN30 + các ngành)": list(dict.fromkeys(BASKETS["⭐ VN30 (Blue-chips HSX)"] + sector_all)),
            **opts}
    return opts


def index_history(code: str, days: int = 400) -> pd.DataFrame:
    """Lịch sử chỉ số, thử các mã thay thế (HNX/UPCOM có nhiều cách viết)."""
    for sym in _INDEX_CANDIDATES.get(code, [code]):
        try:
            df = get_repo().get_price_history(sym, days=days)
            if df is not None and not df.empty and "close" in df.columns:
                return df.sort_values("timestamp").reset_index(drop=True)
        except Exception as exc:  # pragma: no cover - nguồn lỗi
            logger.debug("index history %s failed: %s", sym, exc)
    return pd.DataFrame()


def rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / period, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / period, adjust=False).mean()
    rs = gain / loss.replace(0, np.nan)
    out = 100 - 100 / (1 + rs)
    out[(loss == 0) & (gain > 0)] = 100.0     # chỉ tăng, không phiên giảm
    out[(loss == 0) & (gain == 0)] = 50.0     # đi ngang tuyệt đối
    return out


def period_returns(df: pd.DataFrame) -> Dict[str, Optional[float]]:
    """Hiệu suất 1T, 1Th, 3Th, 6Th, YTD, 1N (%) tính theo giá đóng cửa."""
    out: Dict[str, Optional[float]] = {k: None for k in ("1T", "1Th", "3Th", "6Th", "YTD", "1N")}
    if df is None or df.empty or "close" not in df.columns:
        return out
    s = df.set_index(pd.to_datetime(df["timestamp"]))["close"].astype(float).dropna()
    if len(s) < 2:
        return out
    last_dt, last = s.index[-1], float(s.iloc[-1])

    def ret_since(dt):
        base = s[s.index <= dt]
        if base.empty:
            return None
        b = float(base.iloc[-1])
        return (last / b - 1) * 100 if b else None

    out["1T"] = ret_since(last_dt - pd.Timedelta(days=7))
    out["1Th"] = ret_since(last_dt - pd.Timedelta(days=30))
    out["3Th"] = ret_since(last_dt - pd.Timedelta(days=91))
    out["6Th"] = ret_since(last_dt - pd.Timedelta(days=182))
    out["YTD"] = ret_since(pd.Timestamp(year=last_dt.year, month=1, day=1) - pd.Timedelta(days=1))
    out["1N"] = ret_since(last_dt - pd.Timedelta(days=365)) if s.index[0] <= last_dt - pd.Timedelta(days=360) else None
    return out


def index_card(code: str, df: pd.DataFrame) -> Dict[str, Any]:
    """Số liệu cho thẻ chỉ số: điểm, thay đổi, KL, biên độ, sparkline 60 phiên."""
    name = INDEX_SYMBOLS.get(code, code)
    if df is None or df.empty or len(df) < 2:
        return {"code": code, "name": name, "available": False}
    last, prev = df.iloc[-1], df.iloc[-2]
    close, pclose = float(last["close"]), float(prev["close"])
    chg = close - pclose
    return {
        "code": code, "name": name, "available": True,
        "close": close, "change": chg, "change_pct": chg / pclose * 100 if pclose else 0.0,
        "high": float(last.get("high", close)), "low": float(last.get("low", close)),
        "volume": float(last.get("volume", 0) or 0),
        "date": pd.to_datetime(last["timestamp"]).strftime("%d/%m/%Y"),
        "spark": df["close"].astype(float).tail(60).round(2).tolist(),
        "returns": period_returns(df),
    }


def _symbol_row(sym: str, sectors: Dict[str, str]) -> Optional[Dict[str, Any]]:
    try:
        df = get_repo().get_price_history(sym, days=120)
    except Exception:
        return None
    if df is None or df.empty or len(df) < 2 or "close" not in df.columns:
        return None
    df = df.sort_values("timestamp")
    c = df["close"].astype(float)
    v = df["volume"].astype(float) if "volume" in df.columns else pd.Series(0.0, index=df.index)
    close, prev = float(c.iloc[-1]), float(c.iloc[-2])
    if not prev:
        return None
    avg20 = float(v.iloc[-21:-1].mean()) if len(v) > 2 else float("nan")
    ma20 = float(c.tail(20).mean())
    hi20, lo20 = float(c.iloc[-21:-1].max()) if len(c) > 2 else close, float(c.iloc[-21:-1].min()) if len(c) > 2 else close

    def ret(n):
        return (close / float(c.iloc[-n - 1]) - 1) * 100 if len(c) > n and c.iloc[-n - 1] else None

    return {
        "symbol": sym, "sector": sectors.get(sym, "Khác"),
        "date": pd.to_datetime(df["timestamp"].iloc[-1]),
        "close": close, "prev_close": prev, "change": close - prev, "change_pct": (close / prev - 1) * 100,
        "volume": float(v.iloc[-1]), "value_bn": close * float(v.iloc[-1]) / 1e9,
        "vol_ratio": float(v.iloc[-1]) / avg20 if avg20 and not math.isnan(avg20) else None,
        "ret_5d": ret(5), "ret_20d": ret(20),
        "above_ma20": close > ma20, "new_high20": close > hi20, "new_low20": close < lo20,
        "spark": c.tail(30).round(2).tolist(),
    }


def universe_snapshot(symbols: List[str], workers: int = 8) -> pd.DataFrame:
    """Ảnh chụp phiên gần nhất cho một rổ mã (tải song song, có cache ở tầng repository)."""
    sectors = sector_map()
    syms = list(dict.fromkeys(s.upper() for s in symbols))
    with ThreadPoolExecutor(max_workers=workers) as ex:
        rows = [r for r in ex.map(lambda s: _symbol_row(s, sectors), syms) if r]
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    # Chỉ giữ các mã có phiên cùng ngày với phiên mới nhất (tránh mã ngừng giao dịch làm sai độ rộng)
    latest = df["date"].max()
    df["stale"] = df["date"] < latest - pd.Timedelta(days=3)
    return df


def breadth_stats(snap: pd.DataFrame) -> Dict[str, Any]:
    if snap is None or snap.empty:
        return {"available": False}
    live = snap[~snap["stale"]] if "stale" in snap.columns else snap
    chg = live["change_pct"]
    adv, dec = int((chg > 0.0001).sum()), int((chg < -0.0001).sum())
    unch = int(len(live) - adv - dec)
    return {
        "available": True, "total": int(len(live)),
        "advancing": adv, "declining": dec, "unchanged": unch,
        "ad_ratio": adv / dec if dec else None,
        "pct_above_ma20": float(live["above_ma20"].mean() * 100) if len(live) else None,
        "new_highs": int(live["new_high20"].sum()), "new_lows": int(live["new_low20"].sum()),
        "value_bn": float(live["value_bn"].sum()),
        "avg_change": float(chg.mean()) if len(live) else None,
        "session": live["date"].max().strftime("%d/%m/%Y") if len(live) else "",
    }


def sector_performance(snap: pd.DataFrame) -> pd.DataFrame:
    """Hiệu suất bình quân theo ngành (trung bình gia quyền theo giá trị giao dịch cho 1 phiên)."""
    if snap is None or snap.empty:
        return pd.DataFrame()
    live = snap[~snap["stale"]] if "stale" in snap.columns else snap
    rows = []
    for sec, g in live.groupby("sector"):
        w = g["value_bn"].clip(lower=0)
        d1 = float(np.average(g["change_pct"], weights=w)) if w.sum() > 0 else float(g["change_pct"].mean())
        rows.append({"sector": sec, "n": len(g), "1D": d1,
                     "5D": float(g["ret_5d"].dropna().mean()) if g["ret_5d"].notna().any() else None,
                     "20D": float(g["ret_20d"].dropna().mean()) if g["ret_20d"].notna().any() else None,
                     "value_bn": float(g["value_bn"].sum()),
                     "adv": int((g["change_pct"] > 0).sum()), "dec": int((g["change_pct"] < 0).sum())})
    return pd.DataFrame(rows)


def market_health(index_df: pd.DataFrame, breadth: Dict[str, Any]) -> Dict[str, Any]:
    """
    Điểm sức khỏe thị trường 0–100 theo quy tắc (không phải dự báo):
      Xu hướng 35% (giá so với MA20/50/200) · Động lượng 20% (RSI14) ·
      Độ rộng 30% (% mã tăng, % mã trên MA20) · Hiệu suất 20 phiên 15%.
    """
    comps: Dict[str, Dict[str, Any]] = {}
    if index_df is not None and not index_df.empty and len(index_df) >= 30:
        c = index_df["close"].astype(float).reset_index(drop=True)
        last = float(c.iloc[-1])
        mas = {n: float(c.tail(n).mean()) for n in (20, 50, 200) if len(c) >= n}
        trend = np.mean([100.0 if last > m else 0.0 for m in mas.values()]) if mas else None
        comps["trend"] = {"label": "Xu hướng", "score": trend, "weight": 35,
                          "detail": " · ".join(f"{'▲' if last > m else '▼'} MA{n}" for n, m in mas.items())}
        r = float(rsi(c).iloc[-1])
        if not math.isnan(r):
            comps["momentum"] = {"label": "Động lượng", "score": float(np.clip((r - 30) / 40 * 100, 0, 100)),
                                 "weight": 20, "detail": f"RSI14 = {r:.1f}"}
        if len(c) > 20:
            r20 = (last / float(c.iloc[-21]) - 1) * 100
            comps["perf"] = {"label": "Hiệu suất 20 phiên", "score": float(np.clip(50 + r20 * 6, 0, 100)),
                             "weight": 15, "detail": f"{r20:+.2f}%"}
    if breadth.get("available") and breadth.get("total"):
        adv, dec = breadth["advancing"], breadth["declining"]
        pa = adv / (adv + dec) * 100 if adv + dec else 50.0
        pm = breadth.get("pct_above_ma20") or 0.0
        comps["breadth"] = {"label": "Độ rộng", "score": (pa + pm) / 2, "weight": 30,
                            "detail": f"{pa:.0f}% mã tăng · {pm:.0f}% trên MA20"}
    valid = [v for v in comps.values() if v.get("score") is not None and not math.isnan(v["score"])]
    if not valid:
        return {"available": False, "components": comps}
    score = sum(v["score"] * v["weight"] for v in valid) / sum(v["weight"] for v in valid)
    if score >= 65:
        label = "Tích cực"
    elif score >= 50:
        label = "Trung tính – nghiêng tích cực"
    elif score >= 35:
        label = "Thận trọng"
    else:
        label = "Tiêu cực"
    return {"available": True, "score": float(score), "label": label, "components": comps}
