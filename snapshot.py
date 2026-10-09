"""
ẢNH CHỤP DỮ LIỆU THẬT (snapshot) – dùng khi máy không gọi được API trực tiếp.
- Giá: API chart DNSE (services.entrade.com.vn), giá ĐÃ ĐIỀU CHỈNH, chụp phiên 08/10/2026,
  260 phiên gần nhất + giá đóng cửa cuối mỗi năm 2019–2026 + ATR(14), mã hoá nén (delta) trong data/prices_raw.
- Tin tức: Google News RSS tiếng Việt, chụp ngày 09/10/2026 (5 tin/mã trong 90 ngày, 3 tin/chủ đề thị trường trong 7 ngày).
Định dạng 1 dòng giá:  MÃ|ngày_đầu(epoch day)|giá_đầu×100|ATR14|năm:giá_cuối_năm,...|lịch_phiên|delta_giá×100,...
"""
from __future__ import annotations

import datetime as dt
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd

BASE = Path(__file__).parent / "data"
PRICE_SOURCE = "DNSE chart API (giá điều chỉnh) – ảnh chụp phiên 08/10/2026"
NEWS_SOURCE = "Google News RSS – ảnh chụp 09/10/2026"


@lru_cache(maxsize=1)
def _prices() -> dict:
    rows = []
    for f in sorted((BASE / "prices_raw").glob("*.txt")):
        rows += [l for l in f.read_text(encoding="utf-8").splitlines() if l.strip()]
    days = next(r.split("|")[5] for r in rows if r.split("|")[5] != "D")
    out = {}
    for r in rows:
        sym, day0, c0, atr, ye, dstr, deltas = r.split("|")
        dstr = days if dstr == "D" else dstr
        steps = np.array([int(x) for x in deltas.split(",")])
        closes = np.concatenate([[int(c0)], int(c0) + np.cumsum(steps)]) / 100.0
        gaps = []  # khoảng cách ngày giữa 2 phiên; "0" không thể xảy ra nên "10" = nghỉ 10 ngày (Tết)
        for ch in dstr:
            if ch == "0" and gaps:
                gaps[-1] = gaps[-1] * 10
            else:
                gaps.append(int(ch))
        dnum = np.concatenate([[int(day0)], int(day0) + np.cumsum(gaps)])
        times = pd.to_datetime(dnum, unit="D")
        is_index = sym == "VNINDEX"
        k = 1 if is_index else 1000  # cổ phiếu: nghìn đồng -> đồng
        px = pd.DataFrame({"time": times, "close": closes * k})
        px["open"] = px["high"] = px["low"] = px["close"]
        px["volume"] = np.nan
        out[sym] = dict(
            prices=px[["time", "open", "high", "low", "close", "volume"]],
            atr14=float(atr) * k,
            year_end={int(y): float(v) * k for y, v in (p.split(":") for p in ye.split(","))},
        )
    return out


def has(ticker: str) -> bool:
    return ticker.upper() in _prices()


def tickers() -> list[str]:
    return [t for t in _prices() if t != "VNINDEX"]


def prices(ticker: str) -> dict:
    return _prices()[ticker.upper()]


@lru_cache(maxsize=1)
def _news() -> dict:
    out = {}
    for f in sorted((BASE / "news_raw").glob("*.txt")):
        for line in f.read_text(encoding="utf-8").splitlines():
            if "|" not in line:
                continue
            key, body = line.split("|", 1)
            items = []
            for it in body.split(";;"):
                parts = it.split("~")
                if len(parts) == 3:
                    items.append(dict(date=pd.Timestamp(parts[0]), title=parts[1], source=parts[2], link=""))
            out[key] = pd.DataFrame(items)
    return out


def company_news(ticker: str) -> pd.DataFrame:
    return _news().get(ticker.upper(), pd.DataFrame()).copy()


def market_news() -> pd.DataFrame:
    frames = []
    for k, df in _news().items():
        if k.startswith("M:") and len(df):
            frames.append(df.assign(topic=k[2:]))
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
