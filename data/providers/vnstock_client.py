"""
Vnstock provider – bao bọc thư viện vnstock (ưu tiên API v4, tương thích ngược v3).

API v4 (vnstock >= 4.0, kiểm tra theo mã nguồn 4.0.9):
  Quote(source, symbol).history(start, end, interval)          source: vci | kbs | msn
  Finance(source, symbol, period).income_statement(period=...)  source: vci | kbs
  Company(source, symbol).info() / overview() / news() / events() / shareholders() / officers()
  Listing(source).all_symbols() / symbols_by_industries()
  Trading(source).price_board(symbols_list=[...])

BCTC từ VCI trả về dạng ma trận: cột item / item_en / item_id + mỗi cột là 1 kỳ
("2025", "2025-Q4", có thể trùng dạng "2025-Q4_1"), kỳ mới nhất đứng trước.
KBS trả cùng dạng, item_id đã chuẩn hóa (revenue, net_profit, total_assets…),
giá trị đã quy về VND, nhưng mặc định chỉ 4 kỳ gần nhất.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, List, Optional

import pandas as pd

from data.providers.base_provider import BaseProvider

logger = logging.getLogger(__name__)

_INDEX_ALIAS = {"HNX": "HNXINDEX", "HNX-INDEX": "HNXINDEX", "UPCOM": "UPCOMINDEX",
                "UPCOM-INDEX": "UPCOMINDEX", "UPINDEX": "UPCOMINDEX", "VN-INDEX": "VNINDEX", "VNI": "VNINDEX"}
_STATEMENTS = ("income_statement", "balance_sheet", "cash_flow", "ratio")


def _norm_source(source: str) -> str:
    s = (source or "vci").lower().replace("vnstock_", "")
    return s if s in ("vci", "kbs", "msn") else "vci"


class VnstockClient(BaseProvider):
    """Data provider dùng thư viện vnstock."""

    def __init__(self, source: str = "VCI"):
        self._source = _norm_source(source)
        self._available: Optional[bool] = None
        self._error_message: str = ""
        self._version = "unknown"
        self._major = 0
        try:
            import vnstock
            self._version = getattr(vnstock, "__version__", "unknown")
            try:
                self._major = int(str(self._version).split(".")[0])
            except ValueError:
                self._major = 4
            self._available = True
        except ImportError as exc:
            self._available = False
            self._error_message = (f"vnstock chưa được cài: {exc}. Cài bằng: pip install -U vnstock "
                                   "--extra-index-url https://vnstocks.com/api/simple")

    @property
    def name(self) -> str:
        return "vnstock"

    @property
    def is_available(self) -> bool:
        return bool(self._available)

    # ─────────────────── Helpers ─────────────────────────────────────────────

    def _try(self, label: str, *fns: Callable[[], Any]) -> Any:
        """Chạy lần lượt các cách gọi (v4 rồi v3) cho tới khi có kết quả."""
        if not self.is_available:
            return None
        for fn in fns:
            try:
                res = fn()
                if res is None:
                    continue
                if isinstance(res, pd.DataFrame) and res.empty:
                    continue
                return res
            except Exception as exc:
                self._error_message = f"{label}: {exc}"
                logger.debug("vnstock %s failed: %s", label, exc)
        return None

    # ─────────────────── Price ───────────────────────────────────────────────

    def get_price_history(self, symbol: str, start_date: str, end_date: str,
                          interval: str = "1D", source: Optional[str] = None) -> pd.DataFrame:
        sym = _INDEX_ALIAS.get(self.validate_symbol(symbol), self.validate_symbol(symbol))
        src = _norm_source(source or self._source)

        def v4():
            from vnstock.api.quote import Quote
            return Quote(source=src, symbol=sym).history(start=start_date, end=end_date, interval=interval)

        def v3():
            from vnstock import Vnstock
            return Vnstock().stock(symbol=sym, source=src.upper()).quote.history(
                start=start_date, end=end_date, interval=interval)

        df = self._try(f"history[{src}]", v4, v3)
        if df is None:
            return pd.DataFrame()
        df = df.reset_index(drop="time" not in getattr(df.index, "names", []) and df.index.name not in ("time", "date"))
        df = df.rename(columns={"time": "timestamp", "date": "timestamp", "Date": "timestamp"})
        df = df.loc[:, ~df.columns.duplicated()]
        if "timestamp" not in df.columns:
            return pd.DataFrame()
        df["timestamp"] = pd.to_datetime(df["timestamp"])
        for c in ["open", "high", "low", "close", "volume"]:
            if c in df.columns:
                df[c] = pd.to_numeric(df[c], errors="coerce")
        df["symbol"] = sym
        df["source"] = f"vnstock_{src}"
        return df.dropna(subset=["close"]).reset_index(drop=True)

    def get_index_history(self, index_code: str = "VNINDEX", start_date: str = "",
                          end_date: str = "", interval: str = "1D") -> pd.DataFrame:
        start_date = start_date or (datetime.now() - timedelta(days=365)).strftime("%Y-%m-%d")
        end_date = end_date or datetime.now().strftime("%Y-%m-%d")
        return self.get_price_history(index_code, start_date, end_date, interval)

    def get_current_price(self, symbol: str) -> Optional[Dict[str, Any]]:
        end = datetime.now()
        df = self.get_price_history(symbol, (end - timedelta(days=10)).strftime("%Y-%m-%d"),
                                    end.strftime("%Y-%m-%d"))
        if df.empty:
            return None
        last = df.iloc[-1]
        prev = float(df["close"].iloc[-2]) if len(df) > 1 else None
        price = float(last["close"])
        return {
            "symbol": symbol.upper(), "price": price, "reference_price": prev,
            "change": price - prev if prev else None,
            "change_pct": (price / prev - 1) * 100 if prev else None,
            "volume": float(last.get("volume") or 0), "timestamp": str(last["timestamp"]),
            "source": df["source"].iloc[-1],
        }

    def get_price_board(self, symbols: List[str], source: Optional[str] = None) -> pd.DataFrame:
        src = _norm_source(source or self._source)
        if src == "msn":
            src = "vci"

        def v4():
            from vnstock.api.trading import Trading
            return Trading(source=src).price_board(symbols_list=list(symbols))

        def v3():
            from vnstock import Vnstock
            return Vnstock().stock(symbol=symbols[0], source=src.upper()).trading.price_board(list(symbols))

        df = self._try("price_board", v4, v3)
        if df is None:
            return pd.DataFrame()
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = ["_".join(str(x) for x in c if str(x)) for c in df.columns]
        return df

    # ─────────────────── Financial statements ────────────────────────────────

    def get_financial_statement(self, symbol: str, statement: str, period: str = "year",
                                source: Optional[str] = None) -> pd.DataFrame:
        """
        statement: income_statement | balance_sheet | cash_flow | ratio
        period   : year | quarter
        Trả về bảng thô của nguồn (dạng ma trận item × kỳ); DataRepository chuẩn hóa sau.
        """
        if statement not in _STATEMENTS:
            raise ValueError(statement)
        sym = self.validate_symbol(symbol)
        src = _norm_source(source or self._source)
        if src == "msn":
            return pd.DataFrame()
        period = "year" if period in ("year", "annual", "Y") else "quarter"

        def v4():
            from vnstock.api.financial import Finance
            fin = Finance(source=src, symbol=sym, period=period)
            fn = getattr(fin, statement)
            if src == "vci":
                return fn(period=period, lang="vi", dropna=True)
            return fn(period=period, display_mode=None)   # KBS: giữ item, item_en, item_id

        def v3():
            from vnstock import Vnstock
            fin = Vnstock().stock(symbol=sym, source=src.upper()).finance
            return getattr(fin, statement)(period=period, lang="vi")

        df = self._try(f"{statement}[{src}]", v4, v3)
        if df is None:
            return pd.DataFrame()
        if not isinstance(df, pd.DataFrame):
            df = pd.DataFrame(df)
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = [" ".join(str(x) for x in c if str(x) and not str(x).startswith("Unnamed")).strip()
                          for c in df.columns]
        df.attrs["source"] = f"vnstock_{src}"
        df.attrs["period"] = period
        return df

    # Giữ tên hàm cũ để tương thích code cũ
    def get_income_statement(self, symbol: str, period: str = "quarter", lang: str = "vi") -> pd.DataFrame:
        return self.get_financial_statement(symbol, "income_statement", period)

    def get_balance_sheet(self, symbol: str, period: str = "quarter", lang: str = "vi") -> pd.DataFrame:
        return self.get_financial_statement(symbol, "balance_sheet", period)

    def get_cash_flow(self, symbol: str, period: str = "quarter", lang: str = "vi") -> pd.DataFrame:
        return self.get_financial_statement(symbol, "cash_flow", period)

    def get_financial_ratios(self, symbol: str, period: str = "quarter") -> pd.DataFrame:
        return self.get_financial_statement(symbol, "ratio", period)

    # ─────────────────── Company ─────────────────────────────────────────────

    def _company(self, symbol: str, method: str, source: Optional[str] = None, **kwargs) -> Any:
        sym = self.validate_symbol(symbol)
        src = _norm_source(source or self._source)
        if src == "msn":
            src = "vci"

        def v4():
            from vnstock.api.company import Company
            return getattr(Company(source=src, symbol=sym), method)(**kwargs)

        def v3():
            from vnstock import Vnstock
            comp = Vnstock().stock(symbol=sym, source=src.upper()).company
            return getattr(comp, {"info": "profile"}.get(method, method))(**kwargs)

        return self._try(f"company.{method}[{src}]", v4, v3)

    def get_company_info(self, symbol: str) -> Dict[str, Any]:
        """Hồ sơ doanh nghiệp, chuẩn hóa về các khóa: company_name, short_name, exchange, industry, ..."""
        out: Dict[str, Any] = {}
        for method in ("info", "overview"):
            df = self._company(symbol, method)
            if isinstance(df, pd.DataFrame) and not df.empty:
                row = df.iloc[0].to_dict()
                out.update({k: v for k, v in row.items() if v is not None and not (isinstance(v, float) and pd.isna(v))})
        if not out:
            return {}
        pick = lambda *keys: next((out[k] for k in keys if out.get(k) not in (None, "")), None)  # noqa: E731
        out["company_name"] = pick("company_name", "name", "organ_name", "vi_organ_name", "short_name")
        out["short_name"] = pick("short_name", "organ_short_name")
        out["industry"] = pick("industry", "icb_name3", "icb_name2", "sector", "industry_name")
        out["exchange"] = pick("exchange", "com_group_code", "floor")
        out["description"] = pick("profile", "company_profile", "description", "history")
        out["website"] = pick("website", "web_address", "url")
        out["issue_share"] = pick("issue_share", "issued_share", "outstanding_share", "financial_ratio_issue_share")
        out["symbol"] = symbol.upper()
        return out

    def get_company_overview(self, symbol: str) -> Dict[str, Any]:
        return self.get_company_info(symbol)

    def get_company_news(self, symbol: str) -> List[Dict[str, Any]]:
        """Tin doanh nghiệp từ vnstock (VCI, dự phòng KBS), chuẩn hóa về title/url/published_at/source."""
        items: List[Dict[str, Any]] = []
        for src in ("vci", "kbs"):
            df = self._company(symbol, "news", source=src)
            if not isinstance(df, pd.DataFrame) or df.empty:
                continue
            for _, r in df.iterrows():
                title = r.get("news_title") or r.get("title") or r.get("news_short_content")
                if not title:
                    continue
                pub = r.get("public_date") or r.get("published_date") or r.get("created_at")
                try:
                    pub = pd.to_datetime(pub, unit="ms") if isinstance(pub, (int, float)) else pd.to_datetime(pub)
                except Exception:
                    pub = None
                items.append({
                    "title": str(title).strip(),
                    "url": r.get("news_source_link") or r.get("url") or "",
                    "published_at": pub,
                    "summary": r.get("news_short_content") or r.get("news_sub_title") or "",
                    "source": r.get("news_source") or f"vnstock_{src}",
                })
            if items:
                break
        return items

    def get_company_events(self, symbol: str) -> pd.DataFrame:
        df = self._company(symbol, "events")
        return df if isinstance(df, pd.DataFrame) else pd.DataFrame()

    def get_shareholders(self, symbol: str) -> pd.DataFrame:
        df = self._company(symbol, "shareholders")
        return df if isinstance(df, pd.DataFrame) else pd.DataFrame()

    def get_officers(self, symbol: str) -> pd.DataFrame:
        df = self._company(symbol, "officers")
        return df if isinstance(df, pd.DataFrame) else pd.DataFrame()

    # ─────────────────── Listing ─────────────────────────────────────────────

    def get_all_symbols(self) -> pd.DataFrame:
        src = self._source if self._source in ("vci", "kbs") else "vci"

        def v4():
            from vnstock.api.listing import Listing
            df = Listing(source=src).symbols_by_exchange()
            if df is not None and "type" in df.columns:
                df = df[df["type"].astype(str).str.upper() == "STOCK"]
            return df

        def v4b():
            from vnstock.api.listing import Listing
            return Listing(source=src).all_symbols()

        df = self._try("listing", v4, v4b)
        if df is None:
            import json
            from pathlib import Path
            local = Path(__file__).resolve().parent.parent / "listed_stocks.json"
            if local.exists():
                return pd.DataFrame(json.loads(local.read_text(encoding="utf-8")))
            return pd.DataFrame()
        return df.reset_index(drop=True)

    def get_symbols_by_industries(self) -> pd.DataFrame:
        def v4():
            from vnstock.api.listing import Listing
            return Listing(source="vci").symbols_by_industries()
        df = self._try("symbols_by_industries", v4)
        return df if isinstance(df, pd.DataFrame) else pd.DataFrame()

    def get_symbols_by_exchange(self, exchange: str = "HOSE") -> pd.DataFrame:
        df = self.get_all_symbols()
        if df.empty or "exchange" not in df.columns:
            return pd.DataFrame()
        target = exchange.upper()
        ex = df["exchange"].astype(str).str.upper()
        return df[ex.isin(["HOSE", "HSX"])] if target in ("HOSE", "HSX") else df[ex == target]

    def get_market_overview(self) -> pd.DataFrame:
        syms = self.get_all_symbols()
        if syms.empty or "symbol" not in syms.columns:
            return pd.DataFrame()
        return self.get_price_board(syms["symbol"].astype(str).tolist()[:400])

    def health_check(self) -> Dict[str, Any]:
        res = super().health_check()
        res.update({"version": self._version, "source": self._source})
        if self._error_message:
            res["last_error"] = self._error_message
        return res
