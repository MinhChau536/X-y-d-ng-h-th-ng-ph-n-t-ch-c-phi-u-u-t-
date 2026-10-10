"""
Vietstock Finance provider – NGUỒN DỰ PHÒNG (thử nghiệm).

Vietstock không có API công khai chính thức; client này đọc các endpoint mà
website finance.vietstock.vn dùng nội bộ, nên có thể ngừng hoạt động khi Vietstock
thay đổi trang. Mọi hàm đều trả DataFrame rỗng thay vì ném lỗi để chuỗi dự phòng
của DataRepository tự chuyển sang nguồn kế tiếp.

  Giá lịch sử : api.vietstock.vn/tvnew/history (định dạng UDF giống TradingView)
  BCTC        : finance.vietstock.vn/data/financeinfo (cần token chống CSRF lấy từ trang HTML)
"""
from __future__ import annotations

import logging
import re
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

import pandas as pd
import requests

from config.settings import settings
from data.providers.base_provider import BaseProvider

logger = logging.getLogger(__name__)

FINANCE_BASE = "https://finance.vietstock.vn"
CHART_URL = "https://api.vietstock.vn/tvnew/history"
_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Accept-Language": "vi-VN,vi;q=0.9",
    "Referer": "https://stockchart.vietstock.vn/",
}
# Mã loại báo cáo trên Vietstock
_REPORT_TYPE = {"income_statement": "KQKD", "balance_sheet": "CDKT", "cash_flow": "LC", "ratio": "CSTC"}


class VietstockClient(BaseProvider):

    def __init__(self, session: Optional[requests.Session] = None):
        self._session = session or requests.Session()
        self._session.headers.update(_HEADERS)
        self._token: Optional[str] = None
        self._last_error = ""

    @property
    def name(self) -> str:
        return "Vietstock"

    @property
    def is_available(self) -> bool:
        return True  # chỉ biết khi gọi thật

    # ─────────────────── Price ───────────────────────────────────────────────

    def get_price_history(self, symbol: str, start_date: str, end_date: str,
                          interval: str = "1D") -> pd.DataFrame:
        res = {"1D": "D", "1W": "W", "1M": "M"}.get(interval, "D")
        params = {
            "symbol": symbol.upper(), "resolution": res,
            "from": int(time.mktime(pd.to_datetime(start_date).timetuple())),
            "to": int(time.mktime(pd.to_datetime(end_date).timetuple())) + 86400,
        }
        try:
            r = self._session.get(CHART_URL, params=params, timeout=settings.REQUEST_TIMEOUT)
            if r.status_code != 200:
                self._last_error = f"HTTP {r.status_code}"
                return pd.DataFrame()
            data = r.json()
            if not isinstance(data, dict) or data.get("s") not in (None, "ok") or not data.get("t"):
                return pd.DataFrame()
            df = pd.DataFrame({
                "timestamp": pd.to_datetime(data["t"], unit="s").normalize(),
                "open": data.get("o"), "high": data.get("h"), "low": data.get("l"),
                "close": data.get("c"), "volume": data.get("v"),
            })
            df["symbol"] = symbol.upper()
            df["source"] = "vietstock"
            return df.dropna(subset=["close"])
        except Exception as exc:
            self._last_error = str(exc)
            return pd.DataFrame()

    def get_current_price(self, symbol: str) -> Optional[Dict[str, Any]]:
        end = datetime.now()
        df = self.get_price_history(symbol, (end - pd.Timedelta(days=10)).strftime("%Y-%m-%d"),
                                    end.strftime("%Y-%m-%d"))
        if df.empty:
            return None
        return {"symbol": symbol.upper(), "price": float(df["close"].iloc[-1]),
                "timestamp": str(df["timestamp"].iloc[-1]), "source": "vietstock"}

    # ─────────────────── Financial statements ────────────────────────────────

    def _ensure_token(self, symbol: str) -> Optional[str]:
        if self._token:
            return self._token
        try:
            r = self._session.get(f"{FINANCE_BASE}/{symbol.upper()}/tai-chinh.htm",
                                  timeout=settings.REQUEST_TIMEOUT)
            m = re.search(r'name="__RequestVerificationToken"[^>]*value="([^"]+)"', r.text)
            self._token = m.group(1) if m else None
        except Exception as exc:
            self._last_error = str(exc)
        return self._token

    def get_financial_statement(self, symbol: str, statement: str, period: str = "year",
                                n_periods: int = 8) -> pd.DataFrame:
        report = _REPORT_TYPE.get(statement)
        token = self._ensure_token(symbol) if report else None
        if not token:
            return pd.DataFrame()
        form = {
            "Code": symbol.upper(), "ReportType": report,
            "ReportTermType": "1" if period == "year" else "2",
            "Unit": "1", "Page": "1", "PageSize": str(n_periods),
            "__RequestVerificationToken": token,
        }
        try:
            r = self._session.post(f"{FINANCE_BASE}/data/financeinfo", data=form,
                                   timeout=settings.REQUEST_TIMEOUT)
            if r.status_code != 200:
                self._last_error = f"HTTP {r.status_code}"
                return pd.DataFrame()
            df = self.parse_financeinfo(r.json(), period)
            df.attrs["source"] = "vietstock"
            return df
        except Exception as exc:
            self._last_error = str(exc)
            return pd.DataFrame()

    @staticmethod
    def parse_financeinfo(payload: Any, period: str = "year") -> pd.DataFrame:
        """
        Đọc phản hồi financeinfo một cách "chịu lỗi":
          payload[0] : danh sách kỳ   [{"YearPeriod": 2024, "TermCode": "N"/"Q1"…}, …]
          payload[1] : {"<tên báo cáo>": [{"Name": ..., "NameEn": ..., "Value1": ..., "Value2": ...}, …]}
        Trả về dạng ma trận item × kỳ giống vnstock để dùng chung bộ chuẩn hóa.
        """
        if not isinstance(payload, list) or len(payload) < 2:
            return pd.DataFrame()
        periods_raw, body = payload[0], payload[1]
        labels: List[str] = []
        for p in periods_raw or []:
            y = p.get("YearPeriod") or p.get("Year")
            term = str(p.get("TermCode") or p.get("Term") or "")
            q = re.search(r"([1-4])", term)
            labels.append(f"{y}-Q{q.group(1)}" if (period != "year" and q) else str(y))
        rows = []
        groups = body.values() if isinstance(body, dict) else [body]
        for group in groups:
            for item in group or []:
                if not isinstance(item, dict) or not item.get("Name"):
                    continue
                row = {"item": str(item.get("Name")).strip(), "item_en": item.get("NameEn"),
                       "item_id": item.get("ReportNormID") or item.get("ID")}
                for i, lab in enumerate(labels, start=1):
                    row[lab] = item.get(f"Value{i}")
                rows.append(row)
        return pd.DataFrame(rows)

    def health_check(self) -> Dict[str, Any]:
        res = super().health_check()
        res["last_error"] = self._last_error
        res["note"] = "Nguồn dự phòng thử nghiệm (cào web)"
        return res
