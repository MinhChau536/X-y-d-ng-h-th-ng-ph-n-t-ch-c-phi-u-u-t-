"""
Kho tài liệu doanh nghiệp: Báo cáo thường niên (BCTN) & BCTC dạng PDF theo năm.

Nguồn tìm tài liệu (theo settings.DOCUMENT_SOURCES, có thể đổi thứ tự):
  - vietstock : trang "Tải tài liệu" của mã trên finance.vietstock.vn
  - cafef     : trang/endpoint tài liệu của CafeF
  - website   : trang Quan hệ cổ đông / Nhà đầu tư trên website doanh nghiệp (lấy từ hồ sơ công ty)
  - upload    : người dùng tự tải file lên (luôn hoạt động)
Tất cả đều là đọc trang web công khai → có thể hỏng khi trang đổi cấu trúc; khi đó
người dùng vẫn tải tay hoặc dán link PDF trực tiếp.

Mỗi tài liệu được phân loại tự động (BCTN / BCTC năm / bán niên / quý, hợp nhất / riêng)
và gắn năm, lưu tại data/documents/<MÃ>/ và ghi chỉ mục vào DuckDB.
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple
from urllib.parse import urljoin, urlparse

import pandas as pd
import requests

from config.settings import settings
from data.database import Database
from data.financial_mapping import strip_accents
from data.pdf_financial_extractor import extract_financials, to_wide

logger = logging.getLogger(__name__)

DOC_TYPES = {
    "annual_report": "Báo cáo thường niên",
    "fs_annual": "BCTC năm (kiểm toán)",
    "fs_semiannual": "BCTC bán niên (soát xét)",
    "fs_quarterly": "BCTC quý",
    "other": "Tài liệu khác",
}
_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Accept-Language": "vi-VN,vi;q=0.9,en;q=0.6",
}
_DOC_EXT = (".pdf", ".zip", ".rar", ".doc", ".docx", ".xls", ".xlsx")
_INVESTOR_HINTS = ("quan-he-co-dong", "quan-he-nha-dau-tu", "nha-dau-tu", "co-dong", "investor",
                   "ir", "bao-cao", "tai-lieu", "cong-bo-thong-tin", "shareholder")


# ─────────────────────────────────────────────────────────────────────────────
# Phân loại tài liệu
# ─────────────────────────────────────────────────────────────────────────────

def classify_document(title: str, url: str = "") -> Dict[str, Any]:
    """Suy loại tài liệu, năm, quý, hợp nhất/riêng từ tiêu đề + đường dẫn."""
    text = strip_accents(f"{title} {url}".lower()).replace("_", " ").replace("-", " ")
    doc_type = "other"
    if re.search(r"bao cao thuong nien|annual report|\bbctn\b", text):
        doc_type = "annual_report"
    elif re.search(r"bao cao tai chinh|financial statement|\bbctc\b|\bfs\b", text):
        if re.search(r"ban nien|soat xet|6 thang|semi|interim|giua nien do", text):
            doc_type = "fs_semiannual"
        elif re.search(r"\bquy\s*[1-4]\b|\bq\s*[1-4]\b|quarter", text):
            doc_type = "fs_quarterly"
        else:
            doc_type = "fs_annual"
    years = [int(y) for y in re.findall(r"(?<!\d)(20\d{2}|19\d{2})(?!\d)", text) if int(y) <= datetime.now().year]
    q = re.search(r"(?:quy|q)\s*([1-4])\b", text)
    return {
        "doc_type": doc_type,
        "year": max(years) if years else None,
        "quarter": int(q.group(1)) if (q and doc_type == "fs_quarterly") else None,
        "consolidated": None if doc_type in ("annual_report", "other") else
        (False if re.search(r"\brieng\b|cong ty me|separate", text) else True),
    }


def period_key_for(doc: Dict[str, Any]) -> Optional[int]:
    y = doc.get("year")
    if not y:
        return None
    if doc.get("doc_type") == "fs_quarterly" and doc.get("quarter"):
        return int(y) * 10 + int(doc["quarter"])
    if doc.get("doc_type") == "fs_semiannual":
        return int(y) * 10 + 2
    return int(y) * 10


def _doc_id(symbol: str, url_or_name: str) -> str:
    return hashlib.sha1(f"{symbol}|{url_or_name}".encode("utf-8")).hexdigest()[:16]


# ─────────────────────────────────────────────────────────────────────────────
# Trích link tài liệu từ HTML / JSON
# ─────────────────────────────────────────────────────────────────────────────

def extract_links_from_html(html: str, base_url: str) -> List[Tuple[str, str]]:
    """[(tiêu đề, url tuyệt đối)] cho mọi link tới file tài liệu."""
    out: List[Tuple[str, str]] = []
    try:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "html.parser")
        for a in soup.find_all("a", href=True):
            href = a["href"].strip()
            title = " ".join(a.get_text(" ").split()) or a.get("title") or ""
            out.append((title, urljoin(base_url, href)))
    except Exception:
        for m in re.finditer(r'<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', html, flags=re.I | re.S):
            out.append((re.sub(r"<[^>]+>", " ", m.group(2)).strip(), urljoin(base_url, m.group(1))))
    docs = []
    for title, url in out:
        path = urlparse(url).path.lower()
        if path.endswith(_DOC_EXT) or "download" in path or "file" in path and "." in path.rsplit("/", 1)[-1]:
            docs.append((title or Path(path).name, url))
    return docs


def extract_links_from_json(payload: Any, base_url: str) -> List[Tuple[str, str]]:
    """Duyệt JSON bất kỳ, lấy các cặp (tiêu đề, link file)."""
    found: List[Tuple[str, str]] = []

    def walk(node):
        if isinstance(node, dict):
            url = next((v for k, v in node.items() if isinstance(v, str)
                        and (v.lower().split("?")[0].endswith(_DOC_EXT) or k.lower() in ("link", "url", "fileurl", "filepath"))
                        and ("/" in v)), None)
            if url:
                title = next((str(node[k]) for k in ("Title", "title", "Name", "name", "FileName", "Description", "Desc")
                              if node.get(k)), "")
                found.append((title, urljoin(base_url, url)))
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)
    walk(payload)
    return found


# ─────────────────────────────────────────────────────────────────────────────
# Các nguồn tìm tài liệu
# ─────────────────────────────────────────────────────────────────────────────

class _WebSource:
    name = "web"

    def __init__(self, session: requests.Session):
        self.s = session

    def _get(self, url: str, **kw) -> Optional[requests.Response]:
        try:
            r = self.s.get(url, timeout=12, **kw)
            return r if r.status_code == 200 else None
        except Exception as exc:
            logger.debug("%s GET %s failed: %s", self.name, url, exc)
            return None

    def _collect(self, url: str) -> List[Tuple[str, str]]:
        r = self._get(url)
        if r is None:
            return []
        ctype = r.headers.get("content-type", "")
        if "json" in ctype or r.text[:1] in "[{":
            try:
                return extract_links_from_json(r.json(), url)
            except Exception:
                pass
        return extract_links_from_html(r.text, url)

    def list(self, symbol: str, info: Dict[str, Any]) -> List[Tuple[str, str]]:
        raise NotImplementedError


class VietstockDocs(_WebSource):
    name = "vietstock"

    def list(self, symbol, info):
        out = []
        for url in (f"https://finance.vietstock.vn/{symbol}/tai-tai-lieu.htm",
                    f"https://finance.vietstock.vn/{symbol}/tai-lieu.htm"):
            out += self._collect(url)
        return out


class CafefDocs(_WebSource):
    name = "cafef"

    def list(self, symbol, info):
        out = []
        for url in (f"https://cafef.vn/du-lieu/Ajax/PageNew/FileBCTC.ashx?Symbol={symbol}&Type=1&Year=0",
                    f"https://s.cafef.vn/Ajax/CongTy/BaoCaoTaiChinh.aspx?sym={symbol}"):
            out += self._collect(url)
        return out


class CompanyWebsiteDocs(_WebSource):
    """Dò trang Quan hệ cổ đông trên website doanh nghiệp (tối đa 8 trang, cùng tên miền)."""
    name = "website"

    def list(self, symbol, info):
        site = (info or {}).get("website")
        if not site:
            return []
        if not site.startswith("http"):
            site = "https://" + site.lstrip("/")
        home = self._get(site)
        if home is None:
            return []
        domain = urlparse(home.url).netloc
        docs = extract_links_from_html(home.text, home.url)
        candidates = []
        for title, url in self._all_links(home.text, home.url):
            low = strip_accents(f"{title} {url}".lower())
            if urlparse(url).netloc == domain and any(h in low for h in _INVESTOR_HINTS):
                candidates.append(url)
        for url in list(dict.fromkeys(candidates))[:8]:
            docs += self._collect(url)
        return docs

    @staticmethod
    def _all_links(html: str, base: str) -> List[Tuple[str, str]]:
        return [(re.sub(r"<[^>]+>", " ", t).strip(), urljoin(base, h))
                for h, t in re.findall(r'<a[^>]+href="([^"#]+)"[^>]*>(.*?)</a>', html, flags=re.I | re.S)]


_SOURCES = {"vietstock": VietstockDocs, "cafef": CafefDocs, "website": CompanyWebsiteDocs}


# ─────────────────────────────────────────────────────────────────────────────
# Service
# ─────────────────────────────────────────────────────────────────────────────

class DocumentService:

    def __init__(self, db: Optional[Database] = None, session: Optional[requests.Session] = None,
                 base_dir: Optional[Path] = None):
        self.db = db or Database()
        self.session = session or requests.Session()
        self.session.headers.update(_HEADERS)
        self.base_dir = Path(base_dir or settings.DOCUMENTS_DIR)

    def _dir(self, symbol: str) -> Path:
        d = self.base_dir / symbol.upper()
        d.mkdir(parents=True, exist_ok=True)
        return d

    # ── Tìm tài liệu ──
    def discover(self, symbol: str, company_info: Optional[Dict[str, Any]] = None,
                 sources: Optional[Iterable[str]] = None) -> pd.DataFrame:
        symbol = symbol.upper()
        report: List[str] = []
        seen = set()
        for name in list(sources or settings.DOCUMENT_SOURCES) + ["website"]:
            cls = _SOURCES.get(name)
            if cls is None or name in report:
                continue
            report.append(name)
            try:
                links = cls(self.session).list(symbol, company_info or {})
            except Exception as exc:
                logger.debug("doc source %s failed: %s", name, exc)
                links = []
            for title, url in links:
                if url in seen:
                    continue
                seen.add(url)
                meta = classify_document(title, url)
                if meta["doc_type"] == "other":
                    continue          # chỉ giữ BCTN & BCTC
                self.db.upsert_document({
                    "doc_id": _doc_id(symbol, url), "symbol": symbol, "year": meta["year"],
                    "period": f"Q{meta['quarter']}" if meta["quarter"] else None,
                    "doc_type": meta["doc_type"], "title": title[:300], "url": url, "source": name,
                })
        return self.list_documents(symbol)

    def add_link(self, symbol: str, url: str, title: str = "") -> Dict[str, Any]:
        """Người dùng dán link PDF trực tiếp."""
        meta = classify_document(title or url, url)
        doc = {"doc_id": _doc_id(symbol.upper(), url), "symbol": symbol.upper(), "year": meta["year"],
               "period": f"Q{meta['quarter']}" if meta["quarter"] else None, "doc_type": meta["doc_type"],
               "title": title or Path(urlparse(url).path).name, "url": url, "source": "link"}
        self.db.upsert_document(doc)
        return doc

    def list_documents(self, symbol: str) -> pd.DataFrame:
        df = self.db.get_documents(symbol.upper())
        if not df.empty:
            df["doc_type_label"] = df["doc_type"].map(DOC_TYPES).fillna("Khác")
            df["downloaded"] = df["local_path"].apply(lambda p: bool(p) and Path(str(p)).exists())
        return df

    # ── Tải về / tải lên ──
    def download(self, doc: Dict[str, Any]) -> Optional[Path]:
        url = doc.get("url")
        if not url:
            return None
        try:
            r = self.session.get(url, timeout=60)
            if r.status_code != 200 or not r.content:
                return None
        except Exception as exc:
            logger.warning("Tải tài liệu thất bại %s: %s", url, exc)
            return None
        ext = Path(urlparse(url).path).suffix.lower() or ".pdf"
        if r.content[:4] == b"%PDF":
            ext = ".pdf"
        fname = f"{doc.get('year') or 'na'}_{doc.get('doc_type')}_{doc['doc_id']}{ext}"
        path = self._dir(doc["symbol"]) / fname
        path.write_bytes(r.content)
        self.db.upsert_document({**doc, "local_path": str(path), "size_bytes": len(r.content)})
        return path

    def save_upload(self, symbol: str, filename: str, content: bytes, doc_type: Optional[str] = None,
                    year: Optional[int] = None, quarter: Optional[int] = None) -> Dict[str, Any]:
        meta = classify_document(filename)
        doc_type = doc_type or meta["doc_type"]
        year = year or meta["year"]
        quarter = quarter or meta["quarter"]
        doc_id = _doc_id(symbol.upper(), f"upload:{filename}:{len(content)}")
        path = self._dir(symbol) / f"{year or 'na'}_{doc_type}_{doc_id}{Path(filename).suffix or '.pdf'}"
        path.write_bytes(content)
        doc = {"doc_id": doc_id, "symbol": symbol.upper(), "year": year,
               "period": f"Q{quarter}" if quarter else None, "doc_type": doc_type, "title": filename,
               "url": None, "local_path": str(path), "source": "upload", "size_bytes": len(content)}
        self.db.upsert_document(doc)
        return doc

    # ── Trích số liệu ──
    def extract(self, doc: Dict[str, Any]) -> Dict[str, Any]:
        path = doc.get("local_path")
        if not path or not Path(path).exists():
            return {"values": {}, "note": "Chưa tải tài liệu về máy"}
        if not str(path).lower().endswith(".pdf"):
            return {"values": {}, "note": "Chỉ trích được từ file PDF"}
        res = extract_financials(Path(path).read_bytes())
        res["period_key"] = period_key_for(doc)
        return res

    def pdf_financials(self, symbol: str, period: str = "year") -> pd.DataFrame:
        """Bảng canonical từ các PDF BCTC đã tải (nguồn dự phòng cuối của DataRepository)."""
        docs = self.list_documents(symbol)
        if docs.empty:
            return pd.DataFrame()
        types = ["fs_annual"] if period == "year" else ["fs_quarterly", "fs_semiannual"]
        docs = docs[docs["doc_type"].isin(types) & docs["downloaded"]]
        # Ưu tiên báo cáo hợp nhất: tiêu đề không chứa "riêng"/"công ty mẹ"
        records = []
        for _, d in docs.iterrows():
            meta = classify_document(str(d.get("title") or ""), str(d.get("url") or ""))
            if meta.get("consolidated") is False:
                continue
            res = self.extract(d.to_dict())
            if res.get("values") and res.get("period_key"):
                records.append((res["period_key"], res["values"]))
        return to_wide(records)
