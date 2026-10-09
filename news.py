"""
TIN TỨC DOANH NGHIỆP + CHẤM ĐIỂM CẢM XÚC
- Nguồn 1: vnstock company.news() (tin doanh nghiệp từ Vietcap)
- Nguồn 2 (dự phòng): Google News RSS tiếng Việt
- Cảm xúc: từ điển từ khoá tiếng Việt có trọng số (cách tiếp cận dictionary-based như arminer)
"""
from __future__ import annotations

import datetime as dt
import re
import urllib.parse
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime

import pandas as pd

POSITIVE = {
    "tăng trưởng": 2, "lãi kỷ lục": 3, "kỷ lục": 2, "vượt kế hoạch": 3, "vượt": 1, "lợi nhuận tăng": 3,
    "tăng mạnh": 2, "khởi sắc": 2, "trúng thầu": 2, "hợp đồng": 1, "mở rộng": 1, "chia cổ tức": 2,
    "cổ tức": 1, "nâng hạng": 2, "mua vào": 1, "khối ngoại mua": 2, "tích cực": 1, "hồi phục": 2,
    "bứt phá": 2, "đột biến": 1, "lãi": 1, "hoàn thành": 1, "ký kết": 1, "phát hành thành công": 2,
    "nâng xếp hạng": 2, "khuyến nghị mua": 2, "triển vọng": 1, "doanh thu tăng": 2,
}
NEGATIVE = {
    "lỗ": 2, "thua lỗ": 3, "giảm mạnh": 2, "sụt giảm": 2, "lao dốc": 3, "bán tháo": 3, "phạt": 2,
    "xử phạt": 3, "vi phạm": 2, "khởi tố": 3, "bắt giam": 3, "điều tra": 2, "nợ xấu": 2, "cảnh báo": 2,
    "đình chỉ": 3, "kiểm soát": 1, "hủy niêm yết": 3, "khối ngoại bán": 2, "bán ròng": 1, "chậm trả": 2,
    "giảm": 1, "tiêu cực": 1, "rủi ro": 1, "không đạt": 2, "sa thải": 2, "thoái vốn": 1, "kiện": 2,
}


def sentiment(text: str) -> float:
    t = " " + str(text).lower() + " "
    pos = sum(w * len(re.findall(rf"(?<![\wÀ-ỹ]){re.escape(k)}(?![\wÀ-ỹ])", t)) for k, w in POSITIVE.items())
    neg = sum(w * len(re.findall(rf"(?<![\wÀ-ỹ]){re.escape(k)}(?![\wÀ-ỹ])", t)) for k, w in NEGATIVE.items())
    # "lỗ" nằm trong "lợi nhuận" không bị trùng nhờ ranh giới từ; "lãi" trong "thua lỗ" đã tách riêng
    return 0.0 if pos + neg == 0 else round((pos - neg) / (pos + neg), 2)


def _from_vnstock(ticker: str) -> pd.DataFrame:
    from vnstock import Vnstock
    df = Vnstock().stock(symbol=ticker, source="VCI").company.news()
    df.columns = [str(c).lower() for c in df.columns]
    tcol = next(c for c in df.columns if "title" in c)
    dcol = next((c for c in df.columns if "date" in c or "time" in c), None)
    lcol = next((c for c in df.columns if "url" in c or "link" in c), None)
    out = pd.DataFrame({"title": df[tcol].astype(str)})
    d = df[dcol] if dcol else pd.NaT
    if dcol and pd.api.types.is_numeric_dtype(d):  # epoch ms
        out["date"] = pd.to_datetime(d, unit="ms", errors="coerce")
    else:
        out["date"] = pd.to_datetime(d, errors="coerce")
    out["link"] = df[lcol] if lcol else ""
    out["source"] = "vnstock/Vietcap"
    return out


def _from_google_news(ticker: str, company: str = "") -> pd.DataFrame:
    import requests
    q = f'"{ticker}" cổ phiếu' + (f" OR \"{company}\"" if company and company != ticker else "")
    url = "https://news.google.com/rss/search?" + urllib.parse.urlencode(
        {"q": q, "hl": "vi", "gl": "VN", "ceid": "VN:vi"})
    r = requests.get(url, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
    r.raise_for_status()
    return parse_rss(r.text)


def parse_rss(xml_text: str) -> pd.DataFrame:
    root = ET.fromstring(xml_text)
    rows = []
    for it in root.iter("item"):
        title = (it.findtext("title") or "").strip()
        src = it.find("source")
        try:
            date = parsedate_to_datetime(it.findtext("pubDate") or "")
        except Exception:
            date = None
        rows.append(dict(title=title, date=date, link=it.findtext("link") or "",
                         source=(src.text if src is not None else "Google News")))
    df = pd.DataFrame(rows)
    if len(df):
        df["date"] = pd.to_datetime(df["date"], errors="coerce", utc=True).dt.tz_convert(None)
    return df


def get_news(ticker: str, company: str = "", limit: int = 8, days: int = 90) -> dict:
    """Trả về dict(items=DataFrame, score=-1..1, source=str). Không bao giờ ném lỗi."""
    df, used, errs = pd.DataFrame(), "", []
    for name, fn in (("vnstock", lambda: _from_vnstock(ticker)),
                     ("Google News", lambda: _from_google_news(ticker, company))):
        try:
            df = fn()
            if len(df):
                used = name
                break
        except Exception as e:
            errs.append(f"{name}: {str(e)[:60]}")
    if df.empty:
        return dict(items=df, score=None, source="không lấy được tin (" + "; ".join(errs) + ")", n=0)

    df = df.dropna(subset=["title"]).drop_duplicates("title")
    if df["date"].notna().any():
        cutoff = pd.Timestamp(dt.datetime.now() - dt.timedelta(days=days))
        recent = df[df["date"] >= cutoff]
        df = recent if len(recent) else df
        df = df.sort_values("date", ascending=False)
    df = df.head(limit).copy()
    df["sentiment"] = df["title"].map(sentiment)
    score = round(df["sentiment"].mean(), 2) if len(df) else None
    return dict(items=df.reset_index(drop=True), score=score, source=used, n=len(df))


def demo_news(ticker: str) -> dict:
    titles = [f"{ticker} báo lãi quý tăng trưởng 25%, vượt kế hoạch năm",
              f"{ticker} ký kết hợp đồng mới, mở rộng thị trường",
              f"Khối ngoại bán ròng {ticker} phiên thứ ba liên tiếp",
              f"{ticker} chốt quyền chia cổ tức bằng tiền",
              f"Thị trường giảm mạnh, {ticker} chịu áp lực bán"]
    df = pd.DataFrame({"title": titles, "date": pd.date_range(end=dt.date.today(), periods=5)[::-1],
                       "link": "", "source": "MÔ PHỎNG"})
    df["sentiment"] = df["title"].map(sentiment)
    return dict(items=df, score=round(df["sentiment"].mean(), 2), source="tin MÔ PHỎNG", n=len(df))


# =====================================================================
# TIN TỨC THỊ TRƯỜNG CHUNG (vĩ mô, VN-Index, dòng tiền)
# =====================================================================
MARKET_TOPICS = {
    "Thị trường": "VN-Index thị trường chứng khoán",
    "Khối ngoại": "khối ngoại mua ròng bán ròng chứng khoán",
    "Vĩ mô": "lãi suất tỷ giá Ngân hàng Nhà nước",
    "Nâng hạng": "nâng hạng thị trường chứng khoán Việt Nam",
}
POSITIVE.update({"mua ròng": 2, "nâng hạng": 2, "hạ lãi suất": 2, "giảm lãi suất": 2, "tăng điểm": 2,
                 "thanh khoản tăng": 1, "dòng tiền": 1, "ổn định": 1, "vượt mốc": 2})
NEGATIVE.update({"bán ròng": 2, "tăng lãi suất": 2, "mất điểm": 2, "giảm điểm": 2, "tỷ giá tăng": 1,
                 "căng thẳng": 1, "lạm phát": 1, "hút tiền": 1, "chốt lời": 1})

POSITIVE.update({"tăng trần": 3, "kịch trần": 2, "tiềm năng": 1, "gom": 1, "hút": 1, "dẫn đầu": 2, "hấp dẫn": 2,
                 "nâng dự báo": 2, "tăng vọt": 2, "đánh giá cao": 2, "cơ hội": 1, "khuyến nghị tích cực": 3,
                 "khả quan": 2, "nổi sóng": 2, "ngược dòng": 1, "sáng cửa": 2, "lợi nhuận tăng": 3,
                 "sản lượng": 0, "rót": 1, "hồi phục": 2, "lập đỉnh": 2})
NEGATIVE.update({"bốc hơi": 3, "xả": 2, "thủng": 2, "chìm": 2, "đỏ lửa": 2, "hạ giá mục tiêu": 3, "mất": 1,
                 "bán mạnh": 2, "giảm sàn": 3, "điều chỉnh": 1, "áp lực": 1, "sụt giảm": 2, "rút ròng": 2,
                 "hạn chế chuyển nhượng": 1, "nguy cơ": 2, "đi xuống": 2, "lao": 2, "rời rổ": 2, "ảm đạm": 2, "hụt": 1, "đua nhau bán": 3})

_MARKET_CACHE: dict = {}


def _google_news_query(q: str) -> pd.DataFrame:
    import requests
    url = "https://news.google.com/rss/search?" + urllib.parse.urlencode(
        {"q": q + " when:7d", "hl": "vi", "gl": "VN", "ceid": "VN:vi"})
    r = requests.get(url, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
    r.raise_for_status()
    return parse_rss(r.text)


def get_market_news(per_topic: int = 3) -> dict:
    """Tin thị trường chung 7 ngày gần nhất theo 4 chủ đề + chỉ số tâm lý thị trường. Có bộ nhớ đệm."""
    if "data" in _MARKET_CACHE:
        return _MARKET_CACHE["data"]
    frames, errs = [], []
    for topic, q in MARKET_TOPICS.items():
        try:
            df = _google_news_query(q).head(per_topic)
            df["topic"] = topic
            frames.append(df)
        except Exception as e:
            errs.append(f"{topic}: {str(e)[:40]}")
    if not frames:
        res = dict(items=pd.DataFrame(), score=None, n=0, source="không lấy được (" + "; ".join(errs) + ")")
    else:
        df = pd.concat(frames).drop_duplicates("title").reset_index(drop=True)
        df["sentiment"] = df["title"].map(sentiment)
        res = dict(items=df, score=round(df["sentiment"].mean(), 2), n=len(df), source="Google News (7 ngày)",
                   by_topic=df.groupby("topic")["sentiment"].mean().round(2).to_dict())
    _MARKET_CACHE["data"] = res
    return res


def demo_market_news() -> dict:
    rows = [("Thị trường", "VN-Index tăng điểm, thanh khoản tăng mạnh"),
            ("Thị trường", "Áp lực chốt lời khiến VN-Index giảm điểm cuối phiên"),
            ("Khối ngoại", "Khối ngoại bán ròng phiên thứ 5 liên tiếp"),
            ("Vĩ mô", "Ngân hàng Nhà nước giữ ổn định lãi suất điều hành"),
            ("Nâng hạng", "Kỳ vọng nâng hạng thị trường hỗ trợ dòng tiền ngoại")]
    df = pd.DataFrame(rows, columns=["topic", "title"])
    df["date"] = pd.date_range(end=dt.date.today(), periods=len(df))[::-1]
    df["link"], df["source"] = "", "MÔ PHỎNG"
    df["sentiment"] = df["title"].map(sentiment)
    return dict(items=df, score=round(df["sentiment"].mean(), 2), n=len(df), source="tin MÔ PHỎNG",
                by_topic=df.groupby("topic")["sentiment"].mean().round(2).to_dict())
