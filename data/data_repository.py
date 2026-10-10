"""
DataRepository – lớp truy cập dữ liệu duy nhất của hệ thống (Single Source of Truth).

GIÁ (get_price_history) – ghép nhiều nguồn:
  ┌──────────── phần cũ ────────────┐┌──── DNSE_RECENT_DAYS ngày gần nhất ────┐
  vnstock VCI → KBS → MSN → Vietstock      DNSE (nếu lỗi: dùng nguồn lịch sử)
  - Mọi giá cổ phiếu quy về VND (nguồn báo theo nghìn đồng được nhân 1.000).
  - Ở điểm nối, so sánh các phiên trùng nhau: nếu lệch (do một bên đã điều chỉnh
    cổ tức/chia tách) thì nhân phần cũ với hệ số để chuỗi liền mạch, ghi lại hệ số.
  - Mỗi dòng có cột `source`; attrs["provenance"] tóm tắt nguồn theo đoạn thời gian.

BCTC (get_financials) – chuỗi dự phòng nhiều nguồn:
  vnstock VCI → vnstock KBS → Vietstock → PDF BCTC đã tải (trích theo mã số VAS)
  - Mỗi nguồn được chuẩn hóa về cùng bộ chỉ tiêu (data/financial_mapping.py).
  - Nguồn trước được ưu tiên; ô nào nguồn trước THIẾU (kỳ hoặc chỉ tiêu) thì lấy nguồn sau.
  - Lưu nguồn của từng ô (period × item) để hiển thị và kiểm tra.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from config.settings import settings
from data.cache import cache
from data.data_normalizer import DataNormalizer
from data.database import Database
from data.financial_mapping import (
    STATEMENT_ITEMS, apply_scale, canonicalize, infer_scale, long_to_wide, wide_to_long,
)
from data.providers.dnse_client import DNSEClient, is_index
from data.providers.vietstock_client import VietstockClient
from data.providers.vnstock_client import VnstockClient

logger = logging.getLogger(__name__)
db = Database()
normalizer = DataNormalizer()

_STATEMENT_CODE = {"income_statement": "is", "balance_sheet": "bs", "cash_flow": "cf", "ratio": "ratio"}


def to_vnd(df: pd.DataFrame, symbol: str) -> pd.DataFrame:
    """Cổ phiếu niêm yết VN luôn có giá ≥ 1.000đ; nguồn nào báo < 1.000 là đơn vị nghìn đồng."""
    if df.empty or is_index(symbol):
        return df
    med = pd.to_numeric(df["close"], errors="coerce").median()
    if pd.notna(med) and 0 < med < 1000:
        df = df.copy()
        for c in ("open", "high", "low", "close"):
            if c in df.columns:
                df[c] = pd.to_numeric(df[c], errors="coerce") * 1000.0
    return df


def stitch_prices(recent: pd.DataFrame, older: pd.DataFrame, tolerance: float = 0.005) -> Tuple[pd.DataFrame, Optional[float]]:
    """
    Nối chuỗi cũ với chuỗi gần nhất. Nếu các phiên trùng nhau lệch giá > tolerance
    (thường do một nguồn đã điều chỉnh cổ tức / chia tách còn nguồn kia chưa),
    nhân toàn bộ chuỗi cũ với hệ số k = trung vị(giá mới / giá cũ) trên các phiên trùng.
    Trả về (chuỗi đã nối, hệ số k hoặc None nếu không cần điều chỉnh).
    """
    if older.empty:
        return recent.copy(), None
    if recent.empty:
        return older.copy(), None
    o = older.set_index(pd.to_datetime(older["timestamp"]).dt.normalize())
    r = recent.set_index(pd.to_datetime(recent["timestamp"]).dt.normalize())
    common = o.index.intersection(r.index)
    k = None
    if len(common) >= 1:
        ratio = (r.loc[common, "close"].astype(float) / o.loc[common, "close"].astype(float)).replace([np.inf, -np.inf], np.nan).dropna()
        if not ratio.empty:
            med = float(ratio.median())
            if abs(med - 1.0) > tolerance:
                k = med
    older_part = older[pd.to_datetime(older["timestamp"]).dt.normalize() < r.index.min()].copy()
    if k is not None:
        for c in ("open", "high", "low", "close"):
            if c in older_part.columns:
                older_part[c] = older_part[c].astype(float) * k
        older_part["adjusted"] = True
    out = pd.concat([older_part, recent], ignore_index=True)
    out = out.drop_duplicates(subset=["timestamp"], keep="last").sort_values("timestamp").reset_index(drop=True)
    return out, k


def merge_financial_sources(frames: List[Tuple[str, pd.DataFrame]]) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """
    Gộp nhiều bảng đã chuẩn hóa theo thứ tự ưu tiên.
    frames: [(tên nguồn, bảng rộng)], nguồn đứng trước được ưu tiên.
    Trả về (bảng giá trị, bảng nguồn của từng ô).
    """
    values = pd.DataFrame()
    sources = pd.DataFrame()
    for name, wide in frames:
        if wide is None or wide.empty:
            continue
        src = pd.DataFrame(name, index=wide.index, columns=wide.columns).where(wide.notna())
        if values.empty:
            values, sources = wide.copy(), src
            continue
        values = values.combine_first(wide)
        sources = sources.combine_first(src)
    if not values.empty:
        values = values.sort_index()
        sources = sources.reindex(index=values.index, columns=values.columns)
    return values, sources


def _default_pdf_loader(symbol: str, period: str) -> pd.DataFrame:
    """Số liệu trích từ các PDF BCTC đã tải về kho tài liệu (nguồn dự phòng cuối)."""
    try:
        from services.document_service import DocumentService
        return DocumentService(db=db).pdf_financials(symbol, period)
    except Exception as exc:
        logger.debug("PDF financial loader failed: %s", exc)
        return pd.DataFrame()


class DataRepository:
    """Truy cập dữ liệu: Cache → Nguồn trực tuyến (theo chuỗi ưu tiên) → DuckDB."""

    def __init__(self, vnstock_client: Optional[VnstockClient] = None,
                 dnse_client: Optional[DNSEClient] = None,
                 vietstock_client: Optional[VietstockClient] = None,
                 pdf_financial_loader: Optional[Callable[[str, str], pd.DataFrame]] = None,
                 use_cache: bool = True):
        self._vnstock = vnstock_client or VnstockClient(source=settings.VNSTOCK_SOURCE)
        self._dnse = dnse_client or DNSEClient()
        self._vietstock = vietstock_client or VietstockClient()
        self._pdf_loader = pdf_financial_loader if pdf_financial_loader is not None else _default_pdf_loader
        self._use_cache = use_cache

    # ─────────────────── Cache helpers ───────────────────────────────────────

    def _cget(self, key: str):
        return cache.get(key) if self._use_cache else None

    def _cset(self, key: str, value, ttl: int):
        if self._use_cache:
            cache.set(key, value, ttl=ttl)

    # ─────────────────── Status ──────────────────────────────────────────────

    def get_provider_status(self) -> Dict[str, Any]:
        return {
            "dnse": self._dnse.health_check(),
            "vnstock": self._vnstock.health_check(),
            "vietstock": self._vietstock.health_check(),
            "cache": cache.stats(),
            "strategy": {
                "dnse_recent_days": settings.DNSE_RECENT_DAYS,
                "price_history_sources": settings.PRICE_HISTORY_SOURCES,
                "financial_sources": settings.FINANCIAL_SOURCES,
            },
        }

    # ─────────────────── Price (hybrid) ──────────────────────────────────────

    def _history_from(self, source: str, symbol: str, start: str, end: str, interval: str) -> pd.DataFrame:
        if source.startswith("vnstock"):
            return self._vnstock.get_price_history(symbol, start, end, interval, source=source)
        if source == "vietstock":
            return self._vietstock.get_price_history(symbol, start, end, interval)
        if source == "dnse":
            return self._dnse.get_price_history(symbol, start, end, interval)
        return pd.DataFrame()

    def _history_chain(self, symbol: str, start: str, end: str, interval: str) -> pd.DataFrame:
        for src in settings.PRICE_HISTORY_SOURCES:
            df = self._history_from(src, symbol, start, end, interval)
            if not df.empty:
                return to_vnd(df, symbol)
        return pd.DataFrame()

    def get_price_history(self, symbol: str, start_date: str = "", end_date: str = "",
                          days: int = 365, interval: str = "1D", force_refresh: bool = False) -> pd.DataFrame:
        symbol = symbol.upper().strip()
        end_dt = pd.to_datetime(end_date) if end_date else pd.Timestamp(datetime.now().date())
        start_dt = pd.to_datetime(start_date) if start_date else end_dt - pd.Timedelta(days=days)
        key = f"price2:{symbol}:{start_dt.date()}:{end_dt.date()}:{interval}"
        if not force_refresh:
            cached = self._cget(key)
            if cached is not None and not cached.empty:
                return cached

        cutoff = end_dt - pd.Timedelta(days=settings.DNSE_RECENT_DAYS)
        fmt = "%Y-%m-%d"

        # 1) Đoạn gần nhất từ DNSE
        recent = pd.DataFrame()
        if end_dt >= cutoff:
            recent = to_vnd(self._dnse.get_price_history(symbol, max(start_dt, cutoff).strftime(fmt),
                                                         end_dt.strftime(fmt), interval), symbol)
        # 2) Đoạn cũ (lấy dư 10 ngày để có phiên trùng phục vụ nối chuỗi)
        older = pd.DataFrame()
        older_end = cutoff + pd.Timedelta(days=10) if not recent.empty else end_dt
        if start_dt < cutoff or recent.empty:
            older = self._history_chain(symbol, start_dt.strftime(fmt), older_end.strftime(fmt), interval)

        merged, k = stitch_prices(recent, older)
        if merged.empty:
            logger.warning("Không có dữ liệu giá cho %s từ bất kỳ nguồn nào", symbol)
            return pd.DataFrame()

        if "source" not in merged.columns:
            merged["source"] = "unknown"
        merged["source"] = merged["source"].fillna("unknown")
        df = normalizer.normalize_price(merged, symbol=symbol, interval=interval)   # giữ nguyên cột source
        df = df[(df["timestamp"] >= start_dt) & (df["timestamp"] <= end_dt + pd.Timedelta(days=1))].reset_index(drop=True)

        prov = []
        for src, g in df.groupby("source", sort=False):
            prov.append({"source": src, "from": str(g["timestamp"].min().date()),
                         "to": str(g["timestamp"].max().date()), "rows": int(len(g))})
        df.attrs["provenance"] = prov
        df.attrs["stitch_factor"] = k

        db.upsert_price(df)
        self._cset(key, df, settings.CACHE_TTL_PRICE)
        return df

    def get_current_price(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Giá gần nhất: DNSE trước (cập nhật nhất), dự phòng vnstock rồi Vietstock. Quy về VND."""
        symbol = symbol.upper().strip()
        key = f"current_price2:{symbol}"
        cached = self._cget(key)
        if cached:
            return cached
        data = None
        for getter in (self._dnse.get_current_price, self._vnstock.get_current_price, self._vietstock.get_current_price):
            try:
                data = getter(symbol)
            except Exception as exc:
                logger.debug("current price getter failed: %s", exc)
            if data and data.get("price"):
                break
        if not data:
            return None
        if not is_index(symbol) and 0 < float(data["price"]) < 1000:
            for k in ("price", "reference_price", "change"):
                if data.get(k) is not None:
                    data[k] = float(data[k]) * 1000.0
        self._cset(key, data, settings.CACHE_TTL_MARKET)
        return data

    def get_index_history(self, index_code: str = "VNINDEX", start_date: str = "", days: int = 365) -> pd.DataFrame:
        return self.get_price_history(index_code, start_date=start_date, days=days)

    # ─────────────────── Company ─────────────────────────────────────────────

    def get_company_info(self, symbol: str) -> Dict[str, Any]:
        symbol = symbol.upper().strip()
        key = f"company2:{symbol}"
        cached = self._cget(key)
        if cached:
            return cached
        info = self._vnstock.get_company_info(symbol) or db.get_company(symbol) or {}
        if info:
            info["symbol"] = symbol
            try:
                db.upsert_company(info)
            except Exception:
                pass
            self._cset(key, info, settings.CACHE_TTL_FINANCIAL)
        return info

    def get_company_events(self, symbol: str) -> pd.DataFrame:
        return self._vnstock.get_company_events(symbol)

    def get_shareholders(self, symbol: str) -> pd.DataFrame:
        return self._vnstock.get_shareholders(symbol)

    def get_officers(self, symbol: str) -> pd.DataFrame:
        return self._vnstock.get_officers(symbol)

    def get_vnstock_news(self, symbol: str) -> List[Dict[str, Any]]:
        return self._vnstock.get_company_news(symbol)

    # ─────────────────── Financial statements (multi-source) ─────────────────

    def _raw_statement(self, source: str, symbol: str, statement: str, period: str) -> Tuple[pd.DataFrame, Optional[float]]:
        """Bảng thô từ một nguồn + hệ số đơn vị đã biết của nguồn đó (None = tự đoán)."""
        if source.startswith("vnstock"):
            df = self._vnstock.get_financial_statement(symbol, statement, period, source=source)
            # KBS đã quy về VND; VCI (iq.vietcap) trả VND. Bảng v3 có ghi "(Tỷ đồng)" → nhận diện theo nhãn.
            return df, None
        if source == "vietstock":
            return self._vietstock.get_financial_statement(symbol, statement, period), 1.0
        if source == "pdf" and self._pdf_loader is not None:
            return self._pdf_loader(symbol, period), 1.0
        return pd.DataFrame(), None

    def get_financials(self, symbol: str, period: str = "year", years: int = 10,
                       force_refresh: bool = False) -> Dict[str, Any]:
        """
        BCTC chuẩn hóa nhiều năm, gộp nhiều nguồn.

        Returns dict:
          data      : DataFrame rộng (index = khóa kỳ tăng dần, cột = chỉ tiêu chuẩn, VND)
          sources   : DataFrame cùng kích thước – nguồn của từng ô
          raw       : {statement: {source: bảng thô}} để hiển thị đầy đủ dòng gốc
          attempts  : nhật ký thử từng nguồn (thành công / rỗng / lỗi)
        """
        symbol = symbol.upper().strip()
        period = "year" if period in ("year", "annual", "Y") else "quarter"
        key = f"fin2:{symbol}:{period}"
        if not force_refresh:
            cached = self._cget(key)
            if cached is not None:
                return self._trim(cached, years, period)

        frames: List[Tuple[str, pd.DataFrame]] = []
        raw: Dict[str, Dict[str, pd.DataFrame]] = {}
        attempts: List[Dict[str, Any]] = []
        for source in settings.FINANCIAL_SOURCES:
            per_source: List[pd.DataFrame] = []
            if source == "pdf":
                df, factor = self._raw_statement(source, symbol, "all", period)
                if df is not None and not df.empty:
                    per_source.append(df)       # trình trích PDF đã trả về dạng rộng chuẩn
                attempts.append({"source": source, "statement": "all", "rows": 0 if df is None else len(df)})
            else:
                for statement in ("income_statement", "balance_sheet", "cash_flow", "ratio"):
                    try:
                        df, factor = self._raw_statement(source, symbol, statement, period)
                    except Exception as exc:
                        attempts.append({"source": source, "statement": statement, "error": str(exc)})
                        continue
                    attempts.append({"source": source, "statement": statement, "rows": len(df)})
                    if df is None or df.empty:
                        continue
                    raw.setdefault(statement, {})[source] = df
                    wide = canonicalize(df, _STATEMENT_CODE[statement], unit_factor=factor)
                    wide = self._align_period(wide, period, _STATEMENT_CODE[statement])
                    if not wide.empty:
                        per_source.append(wide)
            if not per_source:
                continue
            combined = per_source[0]
            for w in per_source[1:]:
                combined = combined.combine_first(w)
            if source.startswith("vnstock"):
                combined = apply_scale(combined, infer_scale(combined))
            frames.append((source, combined))

        values, sources = merge_financial_sources(frames)
        if values.empty:
            # Không lấy được trực tuyến → dùng bản đã lưu trong DuckDB (nếu có)
            values, sources = long_to_wide(db.get_financial(symbol, period))
            if not values.empty:
                attempts.append({"source": "duckdb", "statement": "all", "rows": len(values)})
        else:
            db.upsert_financial(symbol, period, wide_to_long(values, sources))

        result = {"symbol": symbol, "period": period, "data": values, "sources": sources,
                  "raw": raw, "attempts": attempts, "fetched_at": datetime.now().isoformat()}
        if not values.empty:
            self._cset(key, result, settings.CACHE_TTL_FINANCIAL)
        return self._trim(result, years, period)

    @staticmethod
    def _align_period(wide: pd.DataFrame, period: str, statement: str = "is") -> pd.DataFrame:
        """
        Chỉ giữ đúng loại kỳ được yêu cầu. Bảng chỉ số của VCI luôn theo quý: khi cần số liệu
        NĂM, các chỉ tiêu số dư (vd số CP lưu hành) lấy giá trị quý cuối cùng có số liệu của năm đó.
        """
        if wide.empty:
            return wide
        q = np.asarray(wide.index, dtype=int) % 10
        if period == "year":
            annual = wide[q == 0]
            quarterly = wide[q > 0]
            if not quarterly.empty:
                by_year = quarterly.groupby(np.asarray(quarterly.index, dtype=int) // 10 * 10).last()
                annual = annual.combine_first(by_year) if not annual.empty else by_year
            return annual.sort_index()
        quarterly = wide[q > 0]
        if statement in ("bs", "ratio") and (q == 0).any():
            # Số dư cuối năm = số dư cuối Q4 → bù cho Q4 khi nguồn chỉ có số năm
            annual = wide[q == 0].copy()
            annual.index = np.asarray(annual.index, dtype=int) + 4
            quarterly = quarterly.combine_first(annual) if not quarterly.empty else annual
        return quarterly.sort_index()

    @staticmethod
    def _trim(result: Dict[str, Any], years: int, period: str) -> Dict[str, Any]:
        data = result.get("data", pd.DataFrame())
        if data is None or data.empty or not years:
            return result
        n = years if period == "year" else years * 4
        out = dict(result)
        out["data"] = data.iloc[-n:]
        src = result.get("sources", pd.DataFrame())
        out["sources"] = src.iloc[-n:] if src is not None and not src.empty else src
        return out

    # Tương thích ngược: các trang/analyzer cũ gọi bảng thô từng loại
    def _legacy(self, symbol: str, statement: str, period: str) -> pd.DataFrame:
        p = "year" if period in ("year", "annual") else "quarter"
        key = f"financial2:{symbol.upper()}:{statement}:{p}"
        cached = self._cget(key)
        if cached is not None and not cached.empty:
            return cached
        for source in settings.FINANCIAL_SOURCES:
            if source == "pdf":
                continue
            df, _ = self._raw_statement(source, symbol.upper(), statement, p)
            if df is not None and not df.empty:
                self._cset(key, df, settings.CACHE_TTL_FINANCIAL)
                return df
        return pd.DataFrame()

    def get_income_statement(self, symbol: str, period: str = "quarter") -> pd.DataFrame:
        return self._legacy(symbol, "income_statement", period)

    def get_balance_sheet(self, symbol: str, period: str = "quarter") -> pd.DataFrame:
        return self._legacy(symbol, "balance_sheet", period)

    def get_cash_flow(self, symbol: str, period: str = "quarter") -> pd.DataFrame:
        return self._legacy(symbol, "cash_flow", period)

    def get_financial_ratios(self, symbol: str, period: str = "quarter") -> pd.DataFrame:
        return self._legacy(symbol, "ratio", period)

    # ─────────────────── Listings ────────────────────────────────────────────

    def get_all_symbols(self) -> pd.DataFrame:
        cached = self._cget("all_symbols2")
        if cached is not None and not cached.empty:
            return cached
        df = self._vnstock.get_all_symbols()
        if not df.empty:
            self._cset("all_symbols2", df, 3600 * 12)
        return df

    def get_symbols_by_industries(self) -> pd.DataFrame:
        cached = self._cget("symbols_icb2")
        if cached is not None and not cached.empty:
            return cached
        df = self._vnstock.get_symbols_by_industries()
        if not df.empty:
            self._cset("symbols_icb2", df, 3600 * 24)
        return df

    def get_price_board(self, symbols: List[str]) -> pd.DataFrame:
        return self._vnstock.get_price_board(symbols)

    # ─────────────────── Portfolio ───────────────────────────────────────────

    def get_portfolio(self, name: str = "default") -> pd.DataFrame:
        return db.get_portfolio(name)

    def add_position(self, portfolio_name: str, symbol: str, quantity: float, buy_price: float,
                     buy_date: str = "", fee_pct: float = 0.0015, notes: str = ""):
        db.add_position(portfolio_name, symbol, quantity, buy_price, buy_date, fee_pct, notes)

    def delete_position(self, position_id: int):
        db.delete_position(position_id)
