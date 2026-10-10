"""
Company News & Intelligence Service.

Thu thập, tổng hợp và chuẩn hóa tin tức doanh nghiệp đa nguồn:
  - Vnstock Company News & Reference Data
  - Google News RSS (Vietstock, CafeF, VnExpress, Tin Nhanh Chứng Khoán, Thanh Niên, Tuổi Trẻ,...)
  - Cổng thông tin tài chính trực tiếp (CafeF, VnExpress, Tin Nhanh Chứng Khoán, VnEconomy)
  - Khử trùng lặp tiêu đề thông minh (SequenceMatcher ratio >= 0.80)
  - Phân loại sắc thái cảm xúc (Sentiment Analysis: Tích cực / Tiêu cực / Trung tính)
  - Bộ nhớ đệm DiskCache + In-Memory tối ưu tốc độ
"""
from __future__ import annotations

import concurrent.futures
from datetime import datetime, timedelta
from difflib import SequenceMatcher
import email.utils
import json
import logging
from pathlib import Path
import re
from typing import Any, Dict, List, Optional
import urllib.request
from urllib.parse import quote, urljoin, urlparse
import xml.etree.ElementTree as ET

import pandas as pd

from config.settings import settings
from data.cache import cache
from data.database import Database

logger = logging.getLogger(__name__)


def get_repo():
    from services.stock_service import get_repo as _g
    return _g()


def news_id(item: Dict[str, Any], symbol: str) -> str:
    import hashlib
    key = (item.get("url") or "").split("#", 1)[0].rstrip("/") or _normalized_title(item.get("title", ""))
    return hashlib.sha1(f"{symbol}|{key}".encode("utf-8")).hexdigest()[:20]

POSITIVE_KEYWORDS = {
    "tăng trưởng", "tăng mạnh", "kỷ lục", "vượt kế hoạch", "mở rộng", "khởi công",
    "hoàn thành", "lợi nhuận tăng", "doanh thu tăng", "đơn hàng mới", "cổ tức",
    "phục hồi", "bứt phá", "mua ròng", "tăng trần", "khởi sắc", "thặng dư", "lãi lớn",
    "nâng hạng", "hợp tác", "đột phá", "triển vọng", "thành công",
}

NEGATIVE_KEYWORDS = {
    "suy giảm", "giảm mạnh", "thua lỗ", "lỗ ròng", "nợ quá hạn", "xử phạt",
    "điều tra", "đình chỉ", "rủi ro", "khó khăn", "chậm tiến độ", "thu hồi",
    "phá sản", "bán tháo", "giảm sàn", "khởi tố", "vi phạm", "lao dốc",
    "hạ giá mục tiêu", "cảnh báo", "thủng đáy",
}

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "vi-VN,vi;q=0.9,en;q=0.7",
}


def _clean_text(val: Any) -> Optional[str]:
    if val is None or pd.isna(val):
        return None
    txt = re.sub(r"\s+", " ", str(val)).strip()
    if txt.lower() in {"", "n/a", "na", "none", "null", "nan", "-"}:
        return None
    return txt


def classify_sentiment(text: str) -> str:
    """Phân loại cảm xúc rule-based theo bộ từ điển tài chính tiếng Việt."""
    low = text.lower()
    pos = sum(kw in low for kw in POSITIVE_KEYWORDS)
    neg = sum(kw in low for kw in NEGATIVE_KEYWORDS)
    if pos > neg:
        return "positive"
    if neg > pos:
        return "negative"
    return "neutral"


def _normalized_title(title: str) -> str:
    return re.sub(r"[^\w\s]", "", title.lower(), flags=re.UNICODE).strip()


def deduplicate_news(items: List[Dict[str, Any]], threshold: float = 0.80) -> List[Dict[str, Any]]:
    """Loại bỏ bài trùng lặp URL hoặc tiêu đề tương tự."""
    result: List[Dict[str, Any]] = []
    seen_urls: set = set()
    seen_titles: List[str] = []

    for item in items:
        title = _clean_text(item.get("title"))
        if not title:
            continue
        url = str(item.get("url") or "").strip()
        canonical_url = url.split("#", 1)[0].rstrip("/")
        if canonical_url and canonical_url in seen_urls:
            continue

        norm = _normalized_title(title)
        if any(SequenceMatcher(None, norm, prev).ratio() >= threshold for prev in seen_titles):
            continue

        if canonical_url:
            seen_urls.add(canonical_url)
        seen_titles.append(norm)
        result.append(item)

    return result


class CompanyNewsService:
    """Service điều phối thu thập và quản lý tin tức doanh nghiệp."""

    def __init__(self):
        pass

    def get_company_news(
        self,
        symbol: str,
        lookback_days: int = 365,
        max_news: int = 40,
        force_refresh: bool = False,
    ) -> Dict[str, Any]:
        """
        Thu thập tin tức đa nguồn cho một mã cổ phiếu.
        """
        symbol = symbol.strip().upper()
        cache_key = f"company_news_data:{symbol}"

        if not force_refresh:
            cached = cache.get(cache_key)
            if cached and isinstance(cached, dict) and cached.get("news"):
                return cached

        # Lấy thông tin công ty để làm từ khóa tìm kiếm
        company_info = get_repo().get_company_info(symbol)
        company_name = company_info.get("company_name", company_info.get("name", symbol))

        articles: List[Dict[str, Any]] = []

        # 1. Thu thập qua Google News RSS (Độ phủ rộng, tức thời, nhiều đầu báo)
        google_news = self._fetch_google_news(symbol, company_name)
        articles.extend(google_news)

        # 2. Thu thập qua vnstock Reference news
        vnstock_news = self._fetch_vnstock_news(symbol)
        articles.extend(vnstock_news)

        # 3. Thu thập qua các cổng tin tài chính CafeF, VnExpress (nếu chưa đủ)
        if len(articles) < 15:
            portal_news = self._fetch_portal_news(symbol, company_name)
            articles.extend(portal_news)

        # 4. Khử trùng lặp và sắp xếp theo thời gian mới nhất
        cleaned_articles = deduplicate_news(articles)

        def get_sort_key(item):
            d = item.get("timestamp_dt")
            if d is None:
                return datetime.min
            if hasattr(d, "tzinfo") and d.tzinfo is not None:
                d = d.replace(tzinfo=None)
            return d

        cleaned_articles.sort(key=get_sort_key, reverse=True)

        final_news = cleaned_articles[:max_news]

        # Thống kê cảm xúc
        pos_count = sum(1 for a in final_news if a.get("sentiment") == "positive")
        neg_count = sum(1 for a in final_news if a.get("sentiment") == "negative")
        neu_count = sum(1 for a in final_news if a.get("sentiment") == "neutral")

        # Trích xuất danh sách nguồn báo thực tế
        sources = sorted(list({a.get("source", "Báo chí") for a in final_news if a.get("source")}))

        result = {
            "symbol": symbol,
            "company_name": company_name,
            "fetched_at": datetime.now().strftime("%d/%m/%Y %H:%M"),
            "news": final_news,
            "sources": sources,
            "summary": {
                "total": len(final_news),
                "positive": pos_count,
                "negative": neg_count,
                "neutral": neu_count,
            },
        }

        # Lưu cache và lưu trữ lâu dài vào DuckDB (để xem lại tin theo ngày)
        cache.set(cache_key, result, ttl=settings.CACHE_TTL_NEWS)
        self.persist(symbol, final_news)
        return result

    # ─────────────────── Lưu trữ & bảng tin ──────────────────────────────────

    def persist(self, symbol: str, items: List[Dict[str, Any]]):
        rows = []
        for it in items:
            rows.append({
                "news_id": news_id(it, symbol), "symbol": symbol, "title": it.get("title"),
                "url": it.get("url"), "source": it.get("source"),
                "published_at": it.get("timestamp_dt"), "sentiment": it.get("sentiment"),
                "summary": (it.get("summary") or "")[:1000],
            })
        Database().upsert_news(rows)

    @staticmethod
    def feed(symbols: Optional[List[str]] = None, days: int = 7, limit: int = 300) -> pd.DataFrame:
        """Bảng tin đã lưu (mọi mã hoặc danh sách mã), mới nhất trước."""
        db = Database()
        if not symbols:
            return db.get_news(days=days, limit=limit)
        frames = [db.get_news(s, days=days, limit=limit) for s in symbols]
        frames = [f for f in frames if not f.empty]
        if not frames:
            return pd.DataFrame()
        df = pd.concat(frames, ignore_index=True)
        order = pd.to_datetime(df["published_at"]).fillna(pd.to_datetime(df["fetched_at"]))
        return df.assign(_o=order).sort_values("_o", ascending=False).drop(columns="_o").head(limit)

    def _fetch_google_news(self, symbol: str, company_name: str) -> List[Dict[str, Any]]:
        """Lấy tin tức thị trường từ Google News RSS."""
        queries = [
            f"cổ phiếu {symbol}",
            f"{symbol} {company_name}",
        ]
        results = []

        for q in queries:
            try:
                enc = quote(q)
                url = f"https://news.google.com/rss/search?q={enc}&hl=vi&gl=VN&ceid=VN:vi"
                req = urllib.request.Request(url, headers=DEFAULT_HEADERS)
                with urllib.request.urlopen(req, timeout=8) as resp:
                    xml_data = resp.read()
                tree = ET.fromstring(xml_data)

                for item in tree.findall(".//item"):
                    raw_title = item.find("title").text if item.find("title") is not None else ""
                    if not raw_title:
                        continue

                    # Tách tiêu đề và nguồn xuất bản
                    if " - " in raw_title:
                        parts = raw_title.rsplit(" - ", 1)
                        title = parts[0].strip()
                        source = parts[1].strip()
                    else:
                        title = raw_title.strip()
                        source = "Báo chí"

                    # Chuẩn hóa tên nguồn phổ biến
                    src_low = source.lower()
                    if "cafef" in src_low:
                        source = "CafeF"
                    elif "vnexpress" in src_low:
                        source = "VnExpress"
                    elif "thanh niên" in src_low:
                        source = "Thanh Niên"
                    elif "vietstock" in src_low:
                        source = "Vietstock"
                    elif "tin nhanh chứng khoán" in src_low or "đầu tư chứng khoán" in src_low:
                        source = "Tin Nhanh Chứng Khoán"
                    elif "vneconomy" in src_low:
                        source = "VnEconomy"
                    elif "tuổi trẻ" in src_low:
                        source = "Tuổi Trẻ"
                    elif "báo đầu tư" in src_low:
                        source = "Báo Đầu Tư"

                    link = item.find("link").text if item.find("link") is not None else ""
                    pub_str = item.find("pubDate").text if item.find("pubDate") is not None else ""

                    # Parse ngày giờ
                    dt = None
                    if pub_str:
                        try:
                            dt = email.utils.parsedate_to_datetime(pub_str)
                            # Convert to local time
                            if dt.tzinfo:
                                dt = dt.astimezone()
                        except Exception:
                            dt = datetime.now()
                    else:
                        dt = datetime.now()

                    date_display = dt.strftime("%d/%m/%Y %H:%M") if dt else datetime.now().strftime("%d/%m/%Y")

                    desc = item.find("description").text if item.find("description") is not None else ""
                    # Bỏ HTML tags trong description
                    desc_clean = re.sub(r"<[^>]+>", "", desc).strip() if desc else ""

                    sentiment = classify_sentiment(f"{title} {desc_clean}")

                    results.append({
                        "title": title,
                        "source": source,
                        "date": date_display,
                        "timestamp_dt": dt,
                        "summary": desc_clean or f"Tin tức sự kiện liên quan đến mã {symbol} ({source}).",
                        "sentiment": sentiment,
                        "url": link,
                    })

            except Exception as e:
                logger.debug("Lỗi lấy Google News cho %s: %s", q, e)

        return results

    def _fetch_vnstock_news(self, symbol: str) -> List[Dict[str, Any]]:
        """Tin doanh nghiệp từ vnstock 4.x (Company(source='vci').news(), dự phòng KBS)."""
        results = []
        try:
            for it in get_repo().get_vnstock_news(symbol):
                title = _clean_text(it.get("title"))
                if not title:
                    continue
                dt = it.get("published_at")
                dt = dt.to_pydatetime() if hasattr(dt, "to_pydatetime") else dt
                summary = _clean_text(it.get("summary")) or ""
                results.append({
                    "title": title,
                    "source": _clean_text(it.get("source")) or "Vnstock",
                    "date": dt.strftime("%d/%m/%Y %H:%M") if dt else "—",
                    "timestamp_dt": dt,
                    "summary": summary,
                    "sentiment": classify_sentiment(f"{title} {summary}"),
                    "url": it.get("url") or "",
                })
        except Exception as e:
            logger.debug("Lỗi vnstock news: %s", e)
        return results

    def _fetch_portal_news(self, symbol: str, company_name: str) -> List[Dict[str, Any]]:
        """Tìm kiếm bổ sung trên CafeF và VnExpress."""
        results = []
        try:
            import requests
            from bs4 import BeautifulSoup

            # CafeF search
            url = f"https://cafef.vn/tim-kiem.chn?keywords={quote(symbol)}&page=1"
            resp = requests.get(url, headers=DEFAULT_HEADERS, timeout=6)
            if resp.ok:
                soup = BeautifulSoup(resp.text[:1_500_000], "html.parser")
                for item in soup.select("div.item, div.news-item, h3 a, h2 a")[:10]:
                    a_tag = item if item.name == "a" else item.find("a")
                    if a_tag and a_tag.get("href"):
                        title = _clean_text(a_tag.get_text())
                        href = a_tag["href"]
                        if title and len(title) > 15 and symbol.lower() in title.lower():
                            full_url = urljoin("https://cafef.vn", href)
                            results.append({
                                "title": title,
                                "source": "CafeF",
                                "date": "—",            # trang tìm kiếm không cho ngày đăng → không tự gán
                                "timestamp_dt": None,
                                "summary": "",
                                "sentiment": classify_sentiment(title),
                                "url": full_url,
                            })
        except Exception as e:
            logger.debug("Lỗi portal news CafeF: %s", e)

        return results
