"""
DNSE market-data client – nguồn giá GẦN NHẤT của hệ thống.

Dùng API biểu đồ công khai của DNSE (Entrade), không cần đăng nhập:
  GET {CHART}/ohlcs/stock?symbol=FPT&resolution=1D&from=<unix>&to=<unix>
  GET {CHART}/ohlcs/index?symbol=VNINDEX&resolution=1D&from=<unix>&to=<unix>
Phản hồi dạng UDF: {"t": [...], "o": [...], "h": [...], "l": [...], "c": [...], "v": [...]}

Giá cổ phiếu DNSE trả về theo đơn vị NGHÌN ĐỒNG (vd 105.5 = 105.500đ); lớp
DataRepository sẽ quy đổi toàn bộ về VND.
"""
from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

import pandas as pd
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from config.settings import settings
from data.providers.base_provider import BaseProvider

logger = logging.getLogger(__name__)

CHART_BASE = "https://services.entrade.com.vn/chart-api/v2"
INDEX_SYMBOLS = {"VNINDEX", "VN30", "HNXINDEX", "HNX30", "UPCOMINDEX", "HNX", "UPCOM", "VN100", "VNXALL"}
_INDEX_ALIAS = {"HNX": "HNXINDEX", "UPCOM": "UPCOMINDEX", "VN-INDEX": "VNINDEX", "VNI": "VNINDEX"}
_RESOLUTION = {"1D": "1D", "1W": "1W", "1M": "1M", "1H": "1H", "30m": "30", "15m": "15", "5m": "5", "1m": "1"}

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Accept": "application/json",
    "Origin": "https://banggia.dnse.com.vn",
    "Referer": "https://banggia.dnse.com.vn/",
}


def is_index(symbol: str) -> bool:
    return symbol.upper().strip() in INDEX_SYMBOLS


class DNSEClient(BaseProvider):
    """Giá OHLCV & giá gần nhất từ DNSE."""

    def __init__(self, session: Optional[requests.Session] = None):
        self._session = session or self._build_session()
        self._available: Optional[bool] = None
        self._last_error: str = ""

    @staticmethod
    def _build_session() -> requests.Session:
        s = requests.Session()
        retry = Retry(total=settings.MAX_RETRIES, backoff_factor=settings.RETRY_BACKOFF,
                      status_forcelist=[429, 500, 502, 503, 504], allowed_methods=["GET"],
                      raise_on_status=False)
        s.mount("https://", HTTPAdapter(max_retries=retry))
        s.headers.update(_HEADERS)
        return s

    @property
    def name(self) -> str:
        return "DNSE"

    @property
    def is_available(self) -> bool:
        if self._available is None:
            end = datetime.now()
            df = self._fetch("VNINDEX", end - timedelta(days=10), end, "1D")
            self._available = not df.empty
        return bool(self._available)

    # ─────────────────── Core fetch ───────────────────────────────────────────

    def _fetch(self, symbol: str, start: datetime, end: datetime, interval: str) -> pd.DataFrame:
        sym = _INDEX_ALIAS.get(symbol.upper().strip(), symbol.upper().strip())
        kind = "index" if is_index(sym) else "stock"
        params = {
            "symbol": sym,
            "resolution": _RESOLUTION.get(interval, "1D"),
            "from": int(time.mktime(start.timetuple())),
            "to": int(time.mktime((end + timedelta(days=1)).timetuple())),
        }
        try:
            resp = self._session.get(f"{CHART_BASE}/ohlcs/{kind}", params=params,
                                     timeout=settings.REQUEST_TIMEOUT)
            if resp.status_code != 200:
                self._last_error = f"HTTP {resp.status_code}"
                return pd.DataFrame()
            return self.parse_udf(resp.json(), sym, interval)
        except Exception as exc:
            self._last_error = str(exc)
            logger.debug("DNSE fetch failed for %s: %s", sym, exc)
            return pd.DataFrame()

    @staticmethod
    def parse_udf(data: Dict[str, Any], symbol: str, interval: str = "1D") -> pd.DataFrame:
        """Chuyển phản hồi UDF {t,o,h,l,c,v} thành DataFrame chuẩn."""
        if not isinstance(data, dict) or not data.get("t"):
            return pd.DataFrame()
        n = len(data["t"])
        df = pd.DataFrame({
            "timestamp": pd.to_datetime(data["t"], unit="s", utc=True)
                           .tz_convert("Asia/Ho_Chi_Minh").tz_localize(None),
            "open": data.get("o", [None] * n),
            "high": data.get("h", [None] * n),
            "low": data.get("l", [None] * n),
            "close": data.get("c", [None] * n),
            "volume": data.get("v", [None] * n),
        })
        if interval in ("1D", "1W", "1M"):
            df["timestamp"] = df["timestamp"].dt.normalize()
        df["symbol"] = symbol.upper()
        df["source"] = "dnse"
        return df.dropna(subset=["close"]).reset_index(drop=True)

    # ─────────────────── Public API ──────────────────────────────────────────

    def get_price_history(self, symbol: str, start_date: str, end_date: str,
                          interval: str = "1D") -> pd.DataFrame:
        start = pd.to_datetime(start_date).to_pydatetime()
        end = pd.to_datetime(end_date).to_pydatetime()
        return self._fetch(symbol, start, end, interval)

    def get_current_price(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Giá khớp gần nhất: nến 1 phút mới nhất trong ngày, nếu không có thì nến ngày gần nhất."""
        end = datetime.now()
        intraday = self._fetch(symbol, end - timedelta(days=3), end, "1m")
        daily = self._fetch(symbol, end - timedelta(days=15), end, "1D")
        if daily.empty and intraday.empty:
            return None
        last = intraday.iloc[-1] if not intraday.empty else daily.iloc[-1]
        prev_close = None
        if not daily.empty:
            last_day = pd.Timestamp(last["timestamp"]).normalize()
            prior = daily[daily["timestamp"] < last_day]
            if not prior.empty:
                prev_close = float(prior["close"].iloc[-1])
        price = float(last["close"])
        change = price - prev_close if prev_close else None
        return {
            "symbol": symbol.upper(),
            "price": price,
            "reference_price": prev_close,
            "change": change,
            "change_pct": (change / prev_close * 100) if (change is not None and prev_close) else None,
            "volume": float(daily["volume"].iloc[-1]) if not daily.empty else None,
            "timestamp": str(last["timestamp"]),
            "source": "dnse",
            "unit": "index_point" if is_index(symbol) else "thousand_vnd",
        }

    def health_check(self) -> Dict[str, Any]:
        res = super().health_check()
        res["base_url"] = CHART_BASE
        res["last_error"] = self._last_error
        return res
