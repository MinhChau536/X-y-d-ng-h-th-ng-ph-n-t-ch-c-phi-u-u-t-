"""
TẦNG 1 + 2: DỮ LIỆU & PHÂN TÍCH
- BCTC: bộ dữ liệu của repo vn-annual-report-miner (fundamentals.py); ngành ICB: danh mục của repo
- Giá & VN-Index: vnstock (VCI); chỉ số vnstock dùng để ĐỐI CHIẾU chéo với BCTC
- Tin tức: news.py (vnstock / Google News) + chấm cảm xúc
- Chấm điểm 4 trụ cột, so sánh ngành, khuyến nghị, giá mục tiêu, cắt lỗ
- Chế độ demo: BCTC thật + giá & tin MÔ PHỎNG (khi không có mạng)
"""
from __future__ import annotations

import datetime as dt
from functools import lru_cache
from pathlib import Path
import numpy as np
import pandas as pd

from fundamentals import get_fundamentals, add_market_multiples, SOURCE_NAME
from news import get_news, demo_news, get_market_news, demo_market_news, sentiment
import snapshot

# =====================================================================
# 1. LẤY DỮ LIỆU
# =====================================================================

def _flatten(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [" | ".join(str(x) for x in c if str(x) != "") for c in df.columns]
    df.columns = [str(c) for c in df.columns]
    return df


def _pick(df: pd.DataFrame, keys, exclude=()):
    """Tìm cột theo từ khoá (không phân biệt hoa thường) vì tên cột vnstock hay đổi."""
    for c in df.columns:
        lc = c.lower()
        if all(k in lc for k in keys) and not any(e in lc for e in exclude):
            return c
    return None


def _year_col(df):
    return _pick(df, ["yearreport"]) or _pick(df, ["năm"]) or _pick(df, ["year"], exclude=["yoy"])



_INDEX_CACHE: dict = {}
COMPANY_FILE = Path(__file__).parent / "data" / "companies_icb.csv"


@lru_cache(maxsize=1)
def companies() -> pd.DataFrame:
    df = pd.read_csv(COMPANY_FILE, encoding="utf-8-sig", dtype=str)
    df.columns = ["ticker", "name", "brand", "exchange", "icb1", "icb2", "icb3", "icb4", "icb_code",
                  "src", "website", "ir"][:len(df.columns)]
    return df.drop_duplicates("ticker").set_index("ticker")


def company_info(ticker: str) -> dict:
    try:
        r = companies().loc[ticker]
        return dict(name=r["name"], industry=f"{r['icb3']} ({r['icb1']})", icb3=r["icb3"],
                    exchange=r["exchange"], website=r.get("website", ""))
    except Exception:
        return dict(name=ticker, industry="", icb3=None, exchange="", website="")


@lru_cache(maxsize=256)
def _peer_row(t: str):
    f = get_fundamentals(t, n_years=2)
    if f.empty:
        return None
    last = f.iloc[-1]
    g = (last["revenue"] / f.iloc[-2]["revenue"] - 1) * 100 if len(f) > 1 and f.iloc[-2]["revenue"] else np.nan
    return dict(ticker=t, roe=last["roe"], net_margin=last["net_margin"], rev_g=g, de=last["de"])


def peer_stats(ticker: str, max_peers: int = 30) -> dict:
    """Trung vị chỉ số của các DN cùng ngành ICB cấp 3 (tính offline từ BCTC)."""
    info = company_info(ticker)
    if not info["icb3"]:
        return {}
    c = companies()
    peers = [t for t in c.index[c["icb3"] == info["icb3"]] if t != ticker][:max_peers]
    rows = [r for r in (_peer_row(t) for t in peers) if r]
    if len(rows) < 3:
        return {}
    df = pd.DataFrame(rows).replace([np.inf, -np.inf], np.nan)
    df = df[(df["roe"].abs() < 100) & (df["net_margin"].abs() < 200)]  # loại giá trị cực đoan
    return dict(n=len(df), group=info["icb3"], roe=df["roe"].median(), net_margin=df["net_margin"].median(),
                rev_g=df["rev_g"].median(), de=df["de"].median(), peers=df)


def _fetch_vnstock(ticker: str, years: int = 6):
    """Giá cổ phiếu + VN-Index (bắt buộc) và bảng chỉ số vnstock (để đối chiếu, không bắt buộc)."""
    from vnstock import Vnstock

    end = dt.date.today()
    start = end - dt.timedelta(days=365 * years)
    stock = Vnstock().stock(symbol=ticker, source="VCI")
    px = stock.quote.history(start=str(start), end=str(end), interval="1D")
    key = (str(start), str(end))
    if key not in _INDEX_CACHE:  # quét nhiều mã chỉ tải VN-Index 1 lần
        _INDEX_CACHE[key] = Vnstock().stock(symbol="VNINDEX", source="VCI").quote.history(
            start=str(start), end=str(end), interval="1D")
    idx = _INDEX_CACHE[key]

    vn_fin = pd.DataFrame()
    try:
        ratio = _flatten(stock.finance.ratio(period="year", lang="en", dropna=True))
        inc = _flatten(stock.finance.income_statement(period="year", lang="en", dropna=True))
        yc = _year_col(ratio)
        vn_fin = pd.DataFrame({"year": pd.to_numeric(ratio[yc], errors="coerce")})
        for k, keys in {"roe": ["roe"], "roa": ["roa"], "net_margin": ["net profit margin"],
                        "de": ["debt/equity"], "pe": ["p/e"], "pb": ["p/b"], "eps": ["eps"],
                        "bvps": ["bvps"]}.items():
            c = _pick(ratio, keys)
            vn_fin[k] = pd.to_numeric(ratio[c], errors="coerce") if c else np.nan
        for k in ["roe", "roa", "net_margin"]:
            s = vn_fin[k].dropna()
            if len(s) and s.abs().median() < 1.5:
                vn_fin[k] = vn_fin[k] * 100
        yc2 = _year_col(inc)
        rev_c = _pick(inc, ["revenue"], exclude=["yoy", "growth", "%"])
        np_c = (_pick(inc, ["attribut", "parent"], exclude=["yoy", "%"])
                or _pick(inc, ["net profit"], exclude=["yoy", "%", "margin"]))
        is_df = pd.DataFrame({"year": pd.to_numeric(inc[yc2], errors="coerce"),
                              "revenue": pd.to_numeric(inc[rev_c], errors="coerce") if rev_c else np.nan,
                              "npat": pd.to_numeric(inc[np_c], errors="coerce") if np_c else np.nan})
        vn_fin = vn_fin.merge(is_df, on="year", how="left").dropna(subset=["year"])
        vn_fin = vn_fin.drop_duplicates("year").sort_values("year")
        vn_fin["year"] = vn_fin["year"].astype(int)
        for k in ["revenue", "npat"]:
            s = vn_fin[k].dropna()
            if len(s) and s.abs().median() > 1e7:
                vn_fin[k] = vn_fin[k] / 1e9
    except Exception as e:
        print(f"[!] {ticker}: không lấy được chỉ số vnstock để đối chiếu ({str(e)[:60]})")
    return _clean_px(px), _clean_px(idx), vn_fin


def _fetch_dnse(symbol: str, years: int = 7) -> pd.DataFrame:
    """Giá ngày trực tiếp từ API chart DNSE (cách lấy dữ liệu của DNSE.py trong repo TELEGRAM-BOT-CHỨNG-KHOÁN)."""
    import requests
    kind = "index" if symbol in ("VNINDEX", "VN30", "HNXINDEX") else "stock"
    end = int(dt.datetime.now().timestamp())
    start = int((dt.datetime.now() - dt.timedelta(days=365 * years)).timestamp())
    r = requests.get(f"https://services.entrade.com.vn/chart-api/v2/ohlcs/{kind}",
                     params=dict(**{"from": start}, to=end, symbol=symbol, resolution="1D"),
                     timeout=15, headers={"User-Agent": "Mozilla/5.0"})
    r.raise_for_status()
    j = r.json()
    if not j.get("t"):
        raise RuntimeError(f"DNSE không có dữ liệu {symbol}")
    px = pd.DataFrame({"time": pd.to_datetime(j["t"], unit="s") + pd.Timedelta(hours=7),
                       "open": j["o"], "high": j["h"], "low": j["l"], "close": j["c"], "volume": j["v"]})
    px["time"] = px["time"].dt.normalize()
    if kind == "stock":
        for c in ["open", "high", "low", "close"]:
            px[c] = px[c] * 1000
    return px


def get_prices(ticker: str, years: int = 7) -> dict:
    """Thứ tự nguồn giá: DNSE trực tiếp -> vnstock -> ảnh chụp dữ liệu thật (snapshot)."""
    errs = []
    try:
        px, idx = _fetch_dnse(ticker, years), _fetch_dnse("VNINDEX", years)
        return dict(prices=px, index=idx, source="DNSE chart API trực tiếp (giá điều chỉnh)", live=True)
    except Exception as e:
        errs.append(f"DNSE: {str(e)[:50]}")
    try:
        px, idx, vn_fin = _fetch_vnstock(ticker, min(years, 6))
        return dict(prices=_scale_stock_px(px), index=idx, vn_fin=vn_fin, source="vnstock – Vietcap (VCI)", live=True)
    except Exception as e:
        errs.append(f"vnstock: {str(e)[:50]}")
    if snapshot.has(ticker):
        sp, si = snapshot.prices(ticker), snapshot.prices("VNINDEX")
        return dict(prices=sp["prices"], index=si["prices"], atr14=sp["atr14"], year_end=sp["year_end"],
                    source=snapshot.PRICE_SOURCE, live=False, errors=errs)
    raise RuntimeError("Không lấy được giá: " + "; ".join(errs))


def _clean_px(px: pd.DataFrame) -> pd.DataFrame:
    px = px.rename(columns=str.lower).copy()
    px["time"] = pd.to_datetime(px["time"])
    px = px.sort_values("time").drop_duplicates("time").reset_index(drop=True)
    return px[["time", "open", "high", "low", "close", "volume"]]


def _scale_stock_px(px: pd.DataFrame) -> pd.DataFrame:
    """VCI trả giá cổ phiếu theo nghìn đồng -> quy về đồng (không áp dụng cho VN-Index)."""
    px = px.copy()
    if px["close"].median() < 1000:
        for c in ["open", "high", "low", "close"]:
            px[c] = px[c] * 1000
    return px


def _demo_prices(ticker: str, years: int, last_price: float):
    """Giá MÔ PHỎNG (chỉ để kiểm thử khi không có API giá)."""
    import zlib
    rng = np.random.default_rng(zlib.crc32(ticker.encode()))
    n = 252 * years
    dates = pd.bdate_range(end=dt.date.today(), periods=n)

    def walk(p_end, mu, sig):
        close = np.exp(np.cumsum(rng.normal(mu, sig, n)))
        close = close / close[-1] * p_end
        high = close * (1 + rng.uniform(0, 0.02, n))
        low = close * (1 - rng.uniform(0, 0.02, n))
        return pd.DataFrame(dict(time=dates, open=(high + low) / 2, high=high, low=low, close=close,
                                 volume=rng.integers(1_000_000, 8_000_000, n)))
    return walk(last_price, 0.0005, 0.018), walk(1_650, 0.0003, 0.011)


def crosscheck(fin: pd.DataFrame, vn_fin: pd.DataFrame) -> pd.DataFrame:
    """Đối chiếu nguồn BCTC chính với vnstock cho 2 năm gần nhất trùng nhau."""
    if vn_fin is None or vn_fin.empty:
        return pd.DataFrame()
    m = fin.merge(vn_fin, on="year", suffixes=("", "_vn"))
    rows = []
    for _, r in m.tail(2).iterrows():
        for k, lbl in [("revenue", "Doanh thu (tỷ)"), ("npat", "LNST (tỷ)"), ("eps", "EPS (đ)"), ("roe", "ROE (%)")]:
            a, b = r.get(k), r.get(k + "_vn")
            if pd.notna(a) and pd.notna(b) and b != 0:
                rows.append(dict(year=int(r["year"]), metric=lbl, main=a, vnstock=b, diff=(a / b - 1) * 100))
    return pd.DataFrame(rows)


def load_data(ticker: str, demo: bool = False, years: int = 6) -> dict:
    ticker = ticker.upper().strip()
    info = company_info(ticker)
    fin = get_fundamentals(ticker)
    notes = list(fin.attrs.get("notes", []))

    if demo:
        last_eps = fin["eps"].iloc[-1] if not fin.empty and fin["eps"].iloc[-1] > 0 else 2_000
        px, idx = _demo_prices(ticker, years, last_eps * 14)
        vn_fin = pd.DataFrame()
        price_src = "GIÁ MÔ PHỎNG (không có kết nối API)"
    else:
        pr = get_prices(ticker)
        px, idx, vn_fin = pr["prices"], pr["index"], pr.get("vn_fin", pd.DataFrame())
        price_src = pr["source"]
        if not pr["live"]:
            notes.append("Không gọi được API trực tiếp, dùng ảnh chụp dữ liệu thật: " + snapshot.PRICE_SOURCE + ".")

    if fin.empty:  # mã không có trong bộ BCTC -> dùng vnstock
        fin = vn_fin.tail(6).reset_index(drop=True)
        fin_src = "vnstock – Vietcap (VCI)"
        notes.append("Mã không có trong bộ BCTC gốc, dùng chỉ số tài chính từ vnstock.")
        if fin.empty:
            raise RuntimeError("Không có dữ liệu BCTC cho mã này")
    else:
        fin = add_market_multiples(fin, px, None if demo else pr.get("year_end"))
        fin_src = SOURCE_NAME

    if demo:
        news_data, market_news = demo_news(ticker), demo_market_news()
    else:
        news_data, market_news = get_news(ticker, info["name"]), get_market_news()
        if not news_data.get("n"):
            df = snapshot.company_news(ticker)
            if len(df):
                df["sentiment"] = df["title"].map(sentiment)
                news_data = dict(items=df, score=round(df["sentiment"].mean(), 2), n=len(df),
                                 source=snapshot.NEWS_SOURCE)
        if not market_news.get("n"):
            df = snapshot.market_news()
            if len(df):
                df["sentiment"] = df["title"].map(sentiment)
                market_news = dict(items=df, score=round(df["sentiment"].mean(), 2), n=len(df),
                                   source=snapshot.NEWS_SOURCE,
                                   by_topic=df.groupby("topic")["sentiment"].mean().round(2).to_dict())
    return dict(
        ticker=ticker, demo=demo, prices=px, index=idx, fin=fin, name=info["name"],
        industry=info["industry"], exchange=info["exchange"], peers=peer_stats(ticker),
        atr14=None if demo else pr.get("atr14"),
        news=news_data, market_news=market_news, check=crosscheck(fin, vn_fin), notes=notes,
        source=f"Giá: {price_src}; BCTC: {fin_src}", price_source=price_src, fin_source=fin_src,
        fetched_at=dt.datetime.now().strftime("%H:%M %d/%m/%Y"),
        last_session=px["time"].iloc[-1].strftime("%d/%m/%Y"),
    )

# =====================================================================
# 2. CHỈ BÁO KỸ THUẬT
# =====================================================================

def add_indicators(px: pd.DataFrame) -> pd.DataFrame:
    px = px.copy()
    px["ma20"] = px["close"].rolling(20).mean()
    px["ma50"] = px["close"].rolling(50).mean()
    px["ma200"] = px["close"].rolling(200).mean()
    delta = px["close"].diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / 14, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / 14, adjust=False).mean()
    px["rsi"] = 100 - 100 / (1 + gain / loss.replace(0, np.nan))
    tr = pd.concat([px["high"] - px["low"],
                    (px["high"] - px["close"].shift()).abs(),
                    (px["low"] - px["close"].shift()).abs()], axis=1).max(axis=1)
    px["atr"] = tr.rolling(14).mean()
    return px


def _ret(s: pd.Series, n: int):
    return s.iloc[-1] / s.iloc[-n - 1] - 1 if len(s) > n else np.nan


# =====================================================================
# 3. CHẤM ĐIỂM 3 TRỤ CỘT + KHUYẾN NGHỊ
# =====================================================================

WEIGHTS = {"quality": 0.35, "valuation": 0.30, "momentum": 0.25, "news": 0.10}


def _check(points, name, cond, pts, value_txt, note=""):
    """Ghi lại từng tiêu chí để in ra bảng giải trình trong PDF."""
    if cond is None:
        points.append(dict(name=name, value=value_txt, ok=None, pts=0, max=0, note="Thiếu dữ liệu"))
    else:
        points.append(dict(name=name, value=value_txt, ok=bool(cond), pts=pts if cond else 0, max=pts, note=note))


def _fmt(x, suf="", d=1):
    return "N/A" if x is None or pd.isna(x) else f"{x:,.{d}f}{suf}"


def analyze(data: dict) -> dict:
    px = add_indicators(data["prices"])
    idx = add_indicators(data["index"])
    fin = data["fin"].copy()
    last = fin.iloc[-1]
    prev = fin.iloc[-2] if len(fin) > 1 else None
    price = px["close"].iloc[-1]

    def nz(x):
        return None if x is None or pd.isna(x) else x

    # --------------------- Trụ cột 1: Chất lượng -----------------------
    q = []
    roe, roa, nm, de = nz(last.get("roe")), nz(last.get("roa")), nz(last.get("net_margin")), nz(last.get("de"))
    rev_g = (last["revenue"] / prev["revenue"] - 1) * 100 if prev is not None and nz(prev["revenue"]) else None
    np_g = (last["npat"] / prev["npat"] - 1) * 100 if prev is not None and nz(prev["npat"]) and prev["npat"] > 0 else None
    is_fin_inst = de is not None and de > 4  # ngân hàng/CTCK: đòn bẩy cao là đặc thù ngành

    _check(q, "ROE ≥ 15%", None if roe is None else roe >= 15, 25, _fmt(roe, "%"))
    _check(q, "ROA ≥ 5%" if not is_fin_inst else "ROA ≥ 1% (tổ chức tài chính)",
           None if roa is None else roa >= (1 if is_fin_inst else 5), 15, _fmt(roa, "%"))
    _check(q, "Biên LN ròng ≥ 10%", None if nm is None else nm >= 10, 15, _fmt(nm, "%"))
    if is_fin_inst:
        _check(q, "Nợ/VCSH (bỏ qua với TCTD)", True, 15, _fmt(de, "x", 2), "Đặc thù ngành tài chính")
    else:
        _check(q, "Nợ/VCSH < 1", None if de is None else de < 1, 15, _fmt(de, "x", 2))
    _check(q, "Tăng trưởng doanh thu ≥ 10%", None if rev_g is None else rev_g >= 10, 15, _fmt(rev_g, "%"))
    _check(q, "Tăng trưởng LNST ≥ 10%", None if np_g is None else np_g >= 10, 15, _fmt(np_g, "%"))
    pr = data.get("peers") or {}
    if pr:
        _check(q, "ROE > trung vị ngành", None if roe is None else roe > pr["roe"], 15,
               f"{_fmt(roe, '%')} vs {_fmt(pr['roe'], '%')}", f"{pr['n']} DN cùng ngành")
        _check(q, "Biên LN > trung vị ngành", None if nm is None else nm > pr["net_margin"], 10,
               f"{_fmt(nm, '%')} vs {_fmt(pr['net_margin'], '%')}", f"{pr['n']} DN cùng ngành")

    # --------------------- Trụ cột 2: Định giá -------------------------
    v = []
    pe_hist = fin["pe"].replace([np.inf, -np.inf], np.nan).dropna()
    pb_hist = fin["pb"].replace([np.inf, -np.inf], np.nan).dropna()
    pe_hist = pe_hist[(pe_hist > 0) & (pe_hist <= 60)]   # loại năm lỗ / lãi gần 0 (P/E vô nghĩa)
    pb_hist = pb_hist[(pb_hist > 0) & (pb_hist <= 15)]
    eps = nz(last.get("eps_adj", last.get("eps")))
    bvps = nz(last.get("bvps_adj", last.get("bvps")))
    pe_now = price / eps if eps and eps > 0 else nz(last.get("pe"))
    pb_now = price / bvps if bvps and bvps > 0 else nz(last.get("pb"))
    pe_med = pe_hist.median() if len(pe_hist) else None
    pb_med = pb_hist.median() if len(pb_hist) else None

    _check(v, "P/E dương (DN có lãi)", None if pe_now is None else pe_now > 0, 20, _fmt(pe_now, "x"))
    _check(v, "P/E < trung vị lịch sử", None if (pe_now is None or pe_med is None) else 0 < pe_now < pe_med,
           30, f"{_fmt(pe_now, 'x')} vs {_fmt(pe_med, 'x')}")
    _check(v, "P/B < trung vị lịch sử", None if (pb_now is None or pb_med is None) else pb_now < pb_med,
           25, f"{_fmt(pb_now, 'x')} vs {_fmt(pb_med, 'x')}")
    _check(v, "P/E < 15x (mức hợp lý chung)", None if pe_now is None else 0 < pe_now < 15, 25, _fmt(pe_now, "x"))

    # Giá mục tiêu = trung bình (EPS × P/E trung vị, BVPS × P/B trung vị)
    targets = []
    if eps and eps > 0 and pe_med:
        targets.append(eps * pe_med)
    if bvps and bvps > 0 and pb_med:
        targets.append(bvps * pb_med)
    target = float(np.mean(targets)) if targets else None
    capped = False
    if target and abs(target / price - 1) > 0.5:  # bội số lịch sử quá xa hiện tại -> giới hạn ±50%
        target = price * (1.5 if target > price else 0.5)
        capped = True
    upside = (target / price - 1) * 100 if target else None

    # --------------------- Trụ cột 3: Động lượng -----------------------
    m = []
    t = px.iloc[-1]
    rs6 = (_ret(px["close"], 126) - _ret(idx["close"], 126)) * 100 if len(px) > 126 and len(idx) > 126 else None
    regime_bull = idx["close"].iloc[-1] > idx["ma200"].iloc[-1] if not pd.isna(idx["ma200"].iloc[-1]) else None

    _check(m, "Giá > MA50", None if pd.isna(t.ma50) else t.close > t.ma50, 20, f"{_fmt(t.close, '', 0)} / {_fmt(t.ma50, '', 0)}")
    _check(m, "MA50 > MA200 (xu hướng tăng)", None if pd.isna(t.ma200) else t.ma50 > t.ma200, 20,
           f"{_fmt(t.ma50, '', 0)} / {_fmt(t.ma200, '', 0)}")
    _check(m, "RSI 40–70 (không quá mua/bán)", None if pd.isna(t.rsi) else 40 <= t.rsi <= 70, 15, _fmt(t.rsi))
    _check(m, "Mạnh hơn VN-Index 6 tháng", None if rs6 is None else rs6 > 0, 25, _fmt(rs6, " điểm %"))
    _check(m, "VN-Index trên MA200 (thị trường thuận)", regime_bull, 20,
           f"{_fmt(idx['close'].iloc[-1], '', 1)} / {_fmt(idx['ma200'].iloc[-1], '', 1)}")

    def score(items):
        mx = sum(i["max"] for i in items)
        return round(100 * sum(i["pts"] for i in items) / mx, 1) if mx else 0.0

    scores = {"quality": score(q), "valuation": score(v), "momentum": score(m)}
    nw = data.get("news") or {}
    mk = data.get("market_news") or {}
    parts = [(nw.get("score"), 0.7), (mk.get("score"), 0.3)]  # 70% tin DN + 30% tâm lý thị trường
    parts = [(sc, wt) for sc, wt in parts if sc is not None]
    if parts:
        senti = sum(sc * wt for sc, wt in parts) / sum(wt for _, wt in parts)
        scores["news"] = round((senti + 1) * 50, 1)  # cảm xúc -1..1 -> 0..100
    w = {k: WEIGHTS[k] for k in scores}
    total = round(sum(scores[k] * w[k] for k in scores) / sum(w.values()), 1)

    if total >= 70 and (upside is None or upside > 0):
        rec, color = "MUA", (16, 128, 64)
    elif total >= 50:
        rec, color = "THEO DÕI / NẮM GIỮ", (200, 140, 0)
    else:
        rec, color = "TRÁNH / BÁN", (190, 30, 45)

    atr = data.get("atr14") or (None if pd.isna(t.atr) else t.atr)
    stop = price - 2 * atr if atr else None

    return dict(
        px=px, idx=idx, fin=fin, price=price,
        checks={"quality": q, "valuation": v, "momentum": m},
        scores=scores, total=total, rec=rec, rec_color=color,
        target=target, upside=upside, stop=stop, atr=atr, target_capped=capped,
        pe_now=pe_now, pb_now=pb_now, pe_med=pe_med, pb_med=pb_med,
        rev_g=rev_g, np_g=np_g, rs6=rs6, regime_bull=regime_bull, rsi=t.rsi,
        ret_1m=_ret(px["close"], 21) * 100, ret_3m=_ret(px["close"], 63) * 100,
        ret_1y=_ret(px["close"], 252) * 100, is_fin_inst=is_fin_inst,
        peers=pr, news=nw, market_news=mk, weights=w,
        comments=_comments(scores, rec, upside, rs6, regime_bull, t.rsi, roe, rev_g, np_g, pr, nw, mk),
    )


def _comments(scores, rec, upside, rs6, bull, rsi, roe, rev_g, np_g, pr=None, nw=None, mk=None):
    """Sinh nhận định tự động bằng tiếng Việt."""
    out = []
    qs = scores["quality"]
    out.append(
        f"Chất lượng doanh nghiệp {'tốt' if qs >= 70 else 'trung bình' if qs >= 45 else 'yếu'} "
        f"({qs:.0f}/100)" + (f", ROE đạt {roe:.1f}%" if roe else "") +
        (f"; doanh thu {'tăng' if rev_g >= 0 else 'giảm'} {abs(rev_g):.1f}%" if rev_g is not None else "") +
        (f", LNST {'tăng' if np_g >= 0 else 'giảm'} {abs(np_g):.1f}% so với năm trước." if np_g is not None else ".")
    )
    if pr and roe is not None:
        out[-1] = out[-1].rstrip(".") + (f"; ROE {'cao hơn' if roe > pr['roe'] else 'thấp hơn'} trung vị ngành "
                                         f"{pr['group']} ({pr['roe']:.1f}%, {pr['n']} DN).")
    vs = scores["valuation"]
    out.append(
        f"Định giá {'hấp dẫn' if vs >= 70 else 'hợp lý' if vs >= 45 else 'đắt'} ({vs:.0f}/100)" +
        (f"; giá mục tiêu hàm ý {'dư địa tăng' if upside >= 0 else 'rủi ro giảm'} {abs(upside):.1f}%"
         + (" (đã giới hạn ±50% do bội số lịch sử lệch xa hiện tại)." if abs(upside) >= 49.9 else ".") if upside is not None else ".")
    )
    ms = scores["momentum"]
    out.append(
        f"Động lượng giá {'mạnh' if ms >= 70 else 'trung tính' if ms >= 45 else 'yếu'} ({ms:.0f}/100)" +
        (f"; cổ phiếu {'vượt' if rs6 > 0 else 'kém'} VN-Index {abs(rs6):.1f} điểm % trong 6 tháng" if rs6 is not None else "") +
        (f", RSI {rsi:.0f}" if not pd.isna(rsi) else "") +
        (f". Thị trường chung đang {'thuận lợi (VN-Index trên MA200)' if bull else 'rủi ro (VN-Index dưới MA200)'}." if bull is not None else ".")
    )
    if nw and nw.get("score") is not None:
        sc = nw["score"]
        out.append(f"Tin tức {nw['n']} bài gần nhất mang sắc thái "
                   f"{'tích cực' if sc > 0.2 else 'tiêu cực' if sc < -0.2 else 'trung tính'} (chỉ số cảm xúc {sc:+.2f}).")
    if mk and mk.get("score") is not None:
        sc = mk["score"]
        bt = mk.get("by_topic", {})
        worst = min(bt, key=bt.get) if bt else None
        best = max(bt, key=bt.get) if bt else None
        out.append(f"Tâm lý thị trường chung {'tích cực' if sc > 0.2 else 'tiêu cực' if sc < -0.2 else 'trung tính'} "
                   f"({sc:+.2f}, {mk['n']} tin 7 ngày)" +
                   (f"; tích cực nhất ở nhóm {best.lower()}, kém nhất ở nhóm {worst.lower()}." if bt and best != worst else "."))
    out.append(f"Tổng hợp: hệ thống đưa ra khuyến nghị {rec}.")
    return out
