"""
Data normalizer – converts raw provider data into the canonical internal schema.

Internal price schema:
  symbol, timestamp, open, high, low, close, volume, value,
  source, interval, adjusted, fetched_at

Key invariants:
  - Prices in VND.
  - Timestamps in Asia/Ho_Chi_Minh, tz-naive (local time stored as-is).
  - Volume in shares (integer).
  - No mixing of adjusted and unadjusted series without explicit flag.
  - No future data in historical series.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

import pandas as pd
import pytz

logger = logging.getLogger(__name__)
HCM_TZ = pytz.timezone("Asia/Ho_Chi_Minh")
PRICE_SCHEMA = ["symbol", "timestamp", "open", "high", "low", "close",
                "volume", "value", "source", "interval", "adjusted", "fetched_at"]


class DataNormalizer:
    """Normalize and validate raw data from any provider."""

    # ─────────────────── Price Data ─────────────────────────────────────────

    @staticmethod
    def normalize_price(df: pd.DataFrame, symbol: str = "", source: str = "",
                        interval: str = "1D", adjusted: bool = False) -> pd.DataFrame:
        """
        Return a clean price DataFrame conforming to the internal schema.

        Parameters
        ----------
        df       : Raw DataFrame from a provider.
        symbol   : Stock ticker override (if not already in df).
        source   : Provider name override.
        interval : Time resolution string.
        adjusted : Whether prices are dividend-adjusted.
        """
        if df is None or df.empty:
            return pd.DataFrame(columns=PRICE_SCHEMA)

        df = df.copy()

        # ── Map common column aliases ──
        col_aliases = {
            "date": "timestamp", "Date": "timestamp", "time": "timestamp",
            "Time": "timestamp", "Datetime": "timestamp", "datetime": "timestamp",
            "Open": "open", "High": "high", "Low": "low", "Close": "close",
            "Volume": "volume", "Value": "value",
        }
        df.rename(columns={k: v for k, v in col_aliases.items() if k in df.columns}, inplace=True)
        df = df.loc[:, ~df.columns.duplicated()]

        # ── Ensure required columns exist ──
        required_cols = ["open", "high", "low", "close", "volume"]
        missing = [c for c in required_cols if c not in df.columns]
        if "close" in missing:
            logger.error("Required column 'close' missing from price DataFrame.")
            return pd.DataFrame(columns=PRICE_SCHEMA)

        # ── Timestamp ──
        if "timestamp" not in df.columns:
            logger.error("No timestamp column found in price DataFrame.")
            return pd.DataFrame(columns=PRICE_SCHEMA)

        df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")

        # Convert to HCM local time (tz-naive storage)
        if df["timestamp"].dt.tz is not None:
            df["timestamp"] = df["timestamp"].dt.tz_convert(HCM_TZ).dt.tz_localize(None)
        # else: assume already local

        # ── Numeric coercion ──
        for col in ["open", "high", "low", "close", "volume", "value"]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")

        # Fill missing value
        if "value" not in df.columns:
            df["value"] = None
        for col in ["open", "high", "low"]:
            if col not in df.columns:
                df[col] = df["close"]

        # ── Metadata columns ──
        if symbol:
            df["symbol"] = symbol.upper()
        elif "symbol" not in df.columns:
            df["symbol"] = ""
        df["symbol"] = df["symbol"].astype(str).str.upper()

        if source:
            df["source"] = source
        elif "source" not in df.columns:
            df["source"] = "unknown"

        df["interval"] = interval
        df["adjusted"] = adjusted

        if "fetched_at" not in df.columns:
            df["fetched_at"] = datetime.now().isoformat()

        # ── Anti-look-ahead guard ──
        now_local = datetime.now()
        future_mask = df["timestamp"] > pd.Timestamp(now_local)
        if future_mask.any():
            logger.warning("Dropping %d future rows for %s", future_mask.sum(), symbol)
            df = df[~future_mask]

        # ── Data quality checks ──
        before = len(df)
        df = df.dropna(subset=["close", "timestamp"])
        df = df[df["close"] > 0]
        df = df.drop_duplicates(subset=["timestamp", "symbol"])
        df = df.sort_values("timestamp").reset_index(drop=True)
        after = len(df)
        if before != after:
            logger.debug("Dropped %d invalid rows for %s", before - after, symbol)

        # Sanity: OHLC consistency
        if all(c in df.columns for c in ["open", "high", "low", "close"]):
            bad = (df["high"] < df["low"]) | (df["close"] > df["high"] * 1.2) | \
                  (df["close"] < df["low"] * 0.8)
            if bad.any():
                logger.warning("%d OHLC inconsistencies detected for %s", bad.sum(), symbol)

        return df[PRICE_SCHEMA]

    # ─────────────────── Financial Data ─────────────────────────────────────

    @staticmethod
    def normalize_financial(df: pd.DataFrame, symbol: str, report_type: str = "consolidated",
                            source: str = "vnstock") -> pd.DataFrame:
        """Normalize financial statement DataFrame."""
        if df is None or df.empty:
            return pd.DataFrame()
        df = df.copy()
        df["symbol"] = symbol.upper()
        df["report_type"] = report_type
        df["source"] = source
        df["fetched_at"] = datetime.now().isoformat()
        return df

    @staticmethod
    def format_currency(value: Optional[float], unit: str = "tỷ") -> str:
        """Format a VND value with unit label."""
        if value is None or pd.isna(value):
            return "N/A"
        if unit == "tỷ":
            return f"{value / 1e9:,.1f} tỷ"
        if unit == "triệu":
            return f"{value / 1e6:,.1f} triệu"
        return f"{value:,.0f}"

    @staticmethod
    def pct_change(new: float, old: float) -> Optional[float]:
        """Safe percentage change calculation."""
        if old is None or old == 0:
            return None
        return (new - old) / abs(old) * 100
