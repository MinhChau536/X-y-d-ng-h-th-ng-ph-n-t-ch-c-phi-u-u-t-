"""
DuckDB-based data repository.

Tables:
  price_daily    – OHLCV day-level data
  price_intraday – intraday OHLCV
  financial_is   – income statement rows
  financial_bs   – balance sheet rows
  financial_cf   – cash flow rows
  financial_ratio– ratios
  company_info   – company metadata
  portfolio      – user portfolio positions
  analysis_log   – history of analyses performed
  reports_log    – history of generated PDF reports
"""
from __future__ import annotations

import logging
import threading
from datetime import datetime
from pathlib import Path
from typing import Optional

import duckdb
import pandas as pd

from config.settings import settings

logger = logging.getLogger(__name__)

DDL = """
CREATE TABLE IF NOT EXISTS price_daily (
    symbol      VARCHAR NOT NULL,
    timestamp   TIMESTAMP NOT NULL,
    open        DOUBLE,
    high        DOUBLE,
    low         DOUBLE,
    close       DOUBLE NOT NULL,
    volume      BIGINT,
    value       DOUBLE,
    source      VARCHAR,
    interval    VARCHAR DEFAULT '1D',
    adjusted    BOOLEAN DEFAULT FALSE,
    fetched_at  TIMESTAMP,
    PRIMARY KEY (symbol, timestamp, adjusted)
);

CREATE TABLE IF NOT EXISTS price_intraday (
    symbol      VARCHAR NOT NULL,
    timestamp   TIMESTAMP NOT NULL,
    open        DOUBLE,
    high        DOUBLE,
    low         DOUBLE,
    close       DOUBLE NOT NULL,
    volume      BIGINT,
    value       DOUBLE,
    source      VARCHAR,
    interval    VARCHAR,
    adjusted    BOOLEAN DEFAULT FALSE,
    fetched_at  TIMESTAMP,
    PRIMARY KEY (symbol, timestamp, interval)
);

CREATE TABLE IF NOT EXISTS financial_is (
    id          INTEGER PRIMARY KEY,
    symbol      VARCHAR NOT NULL,
    period      VARCHAR,
    year        INTEGER,
    quarter     INTEGER,
    report_type VARCHAR DEFAULT 'consolidated',
    source      VARCHAR,
    fetched_at  TIMESTAMP,
    data        JSON
);

CREATE SEQUENCE IF NOT EXISTS seq_financial_is;
ALTER TABLE financial_is ALTER COLUMN id SET DEFAULT nextval('seq_financial_is');

CREATE TABLE IF NOT EXISTS financial_bs (
    id          INTEGER PRIMARY KEY,
    symbol      VARCHAR NOT NULL,
    period      VARCHAR,
    year        INTEGER,
    quarter     INTEGER,
    report_type VARCHAR DEFAULT 'consolidated',
    source      VARCHAR,
    fetched_at  TIMESTAMP,
    data        JSON
);

CREATE SEQUENCE IF NOT EXISTS seq_financial_bs;
ALTER TABLE financial_bs ALTER COLUMN id SET DEFAULT nextval('seq_financial_bs');

CREATE TABLE IF NOT EXISTS financial_cf (
    id          INTEGER PRIMARY KEY,
    symbol      VARCHAR NOT NULL,
    period      VARCHAR,
    year        INTEGER,
    quarter     INTEGER,
    report_type VARCHAR DEFAULT 'consolidated',
    source      VARCHAR,
    fetched_at  TIMESTAMP,
    data        JSON
);

CREATE SEQUENCE IF NOT EXISTS seq_financial_cf;
ALTER TABLE financial_cf ALTER COLUMN id SET DEFAULT nextval('seq_financial_cf');

CREATE TABLE IF NOT EXISTS financial_ratio (
    id          INTEGER PRIMARY KEY,
    symbol      VARCHAR NOT NULL,
    period      VARCHAR,
    year        INTEGER,
    quarter     INTEGER,
    source      VARCHAR,
    fetched_at  TIMESTAMP,
    data        JSON
);

CREATE SEQUENCE IF NOT EXISTS seq_financial_ratio;
ALTER TABLE financial_ratio ALTER COLUMN id SET DEFAULT nextval('seq_financial_ratio');

CREATE TABLE IF NOT EXISTS company_info (
    symbol      VARCHAR PRIMARY KEY,
    name        VARCHAR,
    exchange    VARCHAR,
    sector      VARCHAR,
    industry    VARCHAR,
    founded     VARCHAR,
    employees   INTEGER,
    website     VARCHAR,
    description TEXT,
    source      VARCHAR,
    fetched_at  TIMESTAMP
);

CREATE TABLE IF NOT EXISTS portfolio (
    id          INTEGER PRIMARY KEY,
    portfolio_name VARCHAR DEFAULT 'default',
    symbol      VARCHAR NOT NULL,
    quantity    DOUBLE NOT NULL,
    buy_price   DOUBLE NOT NULL,
    buy_date    DATE,
    fee_pct     DOUBLE DEFAULT 0.0015,
    notes       TEXT,
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE SEQUENCE IF NOT EXISTS seq_portfolio;
ALTER TABLE portfolio ALTER COLUMN id SET DEFAULT nextval('seq_portfolio');

CREATE TABLE IF NOT EXISTS analysis_log (
    id          INTEGER PRIMARY KEY,
    symbol      VARCHAR NOT NULL,
    analysis_type VARCHAR,
    score       DOUBLE,
    summary     TEXT,
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE SEQUENCE IF NOT EXISTS seq_analysis_log;
ALTER TABLE analysis_log ALTER COLUMN id SET DEFAULT nextval('seq_analysis_log');

CREATE TABLE IF NOT EXISTS reports_log (
    id          INTEGER PRIMARY KEY,
    symbol      VARCHAR NOT NULL,
    report_type VARCHAR,
    file_path   VARCHAR,
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE SEQUENCE IF NOT EXISTS seq_reports_log;
ALTER TABLE reports_log ALTER COLUMN id SET DEFAULT nextval('seq_reports_log');

CREATE TABLE IF NOT EXISTS financial_canonical (
    symbol      VARCHAR NOT NULL,
    period_type VARCHAR NOT NULL,
    period_key  INTEGER NOT NULL,
    item        VARCHAR NOT NULL,
    value       DOUBLE,
    source      VARCHAR,
    fetched_at  TIMESTAMP,
    PRIMARY KEY (symbol, period_type, period_key, item)
);

CREATE TABLE IF NOT EXISTS documents (
    doc_id      VARCHAR PRIMARY KEY,
    symbol      VARCHAR NOT NULL,
    year        INTEGER,
    period      VARCHAR,
    doc_type    VARCHAR,
    title       VARCHAR,
    url         VARCHAR,
    local_path  VARCHAR,
    source      VARCHAR,
    size_bytes  BIGINT,
    fetched_at  TIMESTAMP
);

CREATE TABLE IF NOT EXISTS news_items (
    news_id     VARCHAR PRIMARY KEY,
    symbol      VARCHAR,
    title       VARCHAR,
    url         VARCHAR,
    source      VARCHAR,
    published_at TIMESTAMP,
    sentiment   VARCHAR,
    summary     TEXT,
    fetched_at  TIMESTAMP
);

CREATE TABLE IF NOT EXISTS watchlist (
    symbol      VARCHAR PRIMARY KEY,
    note        VARCHAR,
    added_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS price_alerts (
    id          INTEGER PRIMARY KEY,
    symbol      VARCHAR NOT NULL,
    condition   VARCHAR NOT NULL,
    threshold   DOUBLE NOT NULL,
    active      BOOLEAN DEFAULT TRUE,
    triggered_at TIMESTAMP,
    triggered_price DOUBLE,
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE SEQUENCE IF NOT EXISTS seq_price_alerts;
ALTER TABLE price_alerts ALTER COLUMN id SET DEFAULT nextval('seq_price_alerts');

CREATE TABLE IF NOT EXISTS update_log (
    job         VARCHAR,
    status      VARCHAR,
    detail      TEXT,
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
"""


class Database:
    """
    Singleton DuckDB connection manager.

    Kết nối DuckDB không an toàn khi dùng chung giữa nhiều luồng (Streamlit, bộ lọc chạy song song).
    Mỗi luồng vì vậy dùng một cursor riêng (`base.cursor()`), cùng trỏ tới một cơ sở dữ liệu.
    """

    _instance: Optional["Database"] = None

    @property
    def _conn(self):
        base = self.__dict__.get("_base")
        if base is None:
            return None
        local = self.__dict__.setdefault("_local", threading.local())
        cur = getattr(local, "cursor", None)
        if cur is None or getattr(local, "base_id", None) != id(base):
            cur = base if threading.current_thread() is threading.main_thread() else base.cursor()
            local.cursor, local.base_id = cur, id(base)
        return cur

    @_conn.setter
    def _conn(self, value):
        self.__dict__["_base"] = value
        self.__dict__["_local"] = threading.local()

    def __new__(cls, db_path: Optional[str] = None):
        if db_path is not None:
            instance = super().__new__(cls)
            instance._conn = None
            instance._init_db(db_path)
            return instance

        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._conn = None
            cls._instance._init_db()
        return cls._instance

    def _init_db(self, custom_path: Optional[str] = None):
        db_path = custom_path or settings.DB_PATH
        if db_path != ":memory:":
            Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        try:
            self._conn = duckdb.connect(db_path)
            # Run DDL statements one at a time to make errors easier to diagnose
            for stmt in [s.strip() for s in DDL.split(";") if s.strip()]:
                try:
                    self._conn.execute(stmt)
                except Exception as e:
                    # Some statements may already exist — log but continue
                    logger.debug("DDL note: %s", e)
            logger.info("Database initialised at %s", db_path)
        except Exception as exc:
            try:
                # If file is locked by running app, fallback to read-only connection
                self._conn = duckdb.connect(db_path, read_only=True)
                logger.info("Database opened in read-only mode at %s", db_path)
            except Exception:
                logger.warning("DuckDB file lock/WAL error (%s), falling back to in-memory", exc)
                self._conn = duckdb.connect(":memory:")
                for stmt in [s.strip() for s in DDL.split(";") if s.strip()]:
                    try:
                        self._conn.execute(stmt)
                    except Exception:
                        pass

    def close(self):
        """Close connection cleanly."""
        if self._conn:
            try:
                self._conn.close()
            except Exception:
                pass

    @property
    def conn(self) -> duckdb.DuckDBPyConnection:
        return self._conn

    # ─────────────────── Price ───────────────────────────────────────────────

    def upsert_price(self, df: pd.DataFrame, table: str = "price_daily"):
        """Insert-or-replace price rows matching existing columns."""
        if df.empty:
            return
        try:
            tbl_info = self._conn.execute(f"PRAGMA table_info('{table}')").df()
            tbl_cols = tbl_info["name"].tolist()
            common_cols = [c for c in tbl_cols if c in df.columns]
            if not common_cols:
                return
            cols_str = ", ".join(common_cols)
            self._conn.register("_tmp_price", df[common_cols])
            self._conn.execute(f"""
                INSERT OR REPLACE INTO {table} ({cols_str})
                SELECT {cols_str} FROM _tmp_price
            """)
            self._conn.unregister("_tmp_price")
        except Exception as exc:
            logger.error("upsert_price failed: %s", exc)

    def get_price(self, symbol: str, start: Optional[str] = None, end: Optional[str] = None,
                  table: str = "price_daily") -> pd.DataFrame:
        try:
            query = f"SELECT * FROM {table} WHERE symbol = ?"
            params = [symbol.upper()]
            if start:
                query += " AND timestamp >= ?"
                params.append(start)
            if end:
                query += " AND timestamp <= ?"
                params.append(end)
            query += " ORDER BY timestamp"
            return self._conn.execute(query, params).df()
        except Exception as exc:
            logger.error("get_price failed: %s", exc)
            return pd.DataFrame()

    # ─────────────────── Company ─────────────────────────────────────────────

    def upsert_company(self, info: dict):
        try:
            self._conn.execute("""
                INSERT OR REPLACE INTO company_info
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, [
                info.get("symbol", ""),
                info.get("name", ""),
                info.get("exchange", ""),
                info.get("sector", ""),
                info.get("industry", ""),
                info.get("founded", ""),
                info.get("employees"),
                info.get("website", ""),
                info.get("description", ""),
                info.get("source", ""),
                datetime.now(),
            ])
        except Exception as exc:
            logger.error("upsert_company failed: %s", exc)

    def get_company(self, symbol: str) -> dict:
        try:
            row = self._conn.execute(
                "SELECT * FROM company_info WHERE symbol = ?", [symbol.upper()]
            ).fetchone()
            if not row:
                return {}
            cols = [d[0] for d in self._conn.description]
            return dict(zip(cols, row))
        except Exception:
            return {}

    # ─────────────────── Portfolio ───────────────────────────────────────────

    def add_position(self, portfolio_name: str, symbol: str, quantity: float,
                     buy_price: float, buy_date: str = "", fee_pct: float = 0.0015,
                     notes: str = ""):
        try:
            self._conn.execute(
                "INSERT INTO portfolio (portfolio_name, symbol, quantity, buy_price, buy_date, fee_pct, notes) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                [portfolio_name, symbol.upper(), quantity, buy_price, buy_date, fee_pct, notes],
            )
        except Exception as exc:
            logger.error("add_position failed: %s", exc)

    def get_portfolio(self, portfolio_name: str = "default") -> pd.DataFrame:
        try:
            return self._conn.execute(
                "SELECT * FROM portfolio WHERE portfolio_name = ? ORDER BY created_at",
                [portfolio_name],
            ).df()
        except Exception:
            return pd.DataFrame()

    def delete_position(self, position_id: int):
        try:
            self._conn.execute("DELETE FROM portfolio WHERE id = ?", [position_id])
        except Exception as exc:
            logger.error("delete_position failed: %s", exc)

    # ─────────────────── Analysis Log ────────────────────────────────────────

    def log_analysis(self, symbol: str, analysis_type: str, score: float, summary: str):
        try:
            self._conn.execute(
                "INSERT INTO analysis_log (symbol, analysis_type, score, summary) VALUES (?, ?, ?, ?)",
                [symbol.upper(), analysis_type, score, summary],
            )
        except Exception as exc:
            logger.error("log_analysis failed: %s", exc)

    def get_analysis_history(self, symbol: str = "", limit: int = 50) -> pd.DataFrame:
        try:
            if symbol:
                return self._conn.execute(
                    "SELECT * FROM analysis_log WHERE symbol = ? ORDER BY created_at DESC LIMIT ?",
                    [symbol.upper(), limit],
                ).df()
            return self._conn.execute(
                "SELECT * FROM analysis_log ORDER BY created_at DESC LIMIT ?", [limit]
            ).df()
        except Exception:
            return pd.DataFrame()

    # ─────────────────── Reports Log ─────────────────────────────────────────

    def log_report(self, symbol: str, report_type: str, file_path: str):
        try:
            self._conn.execute(
                "INSERT INTO reports_log (symbol, report_type, file_path) VALUES (?, ?, ?)",
                [symbol.upper(), report_type, file_path],
            )
        except Exception as exc:
            logger.error("log_report failed: %s", exc)

    def get_reports_history(self, limit: int = 50) -> pd.DataFrame:
        try:
            return self._conn.execute(
                "SELECT * FROM reports_log ORDER BY created_at DESC LIMIT ?", [limit]
            ).df()
        except Exception:
            return pd.DataFrame()

    # ─────────────────── Financial (canonical, long format) ──────────────────

    def upsert_financial(self, symbol: str, period_type: str, long_df: pd.DataFrame):
        """long_df columns: period_key, item, value, source."""
        if long_df is None or long_df.empty:
            return
        try:
            df = long_df[["period_key", "item", "value", "source"]].copy()
            df.insert(0, "period_type", period_type)
            df.insert(0, "symbol", symbol.upper())
            df["fetched_at"] = datetime.now()
            self._conn.register("_tmp_fin", df)
            self._conn.execute(
                "INSERT OR REPLACE INTO financial_canonical "
                "SELECT symbol, period_type, CAST(period_key AS INTEGER), item, value, source, fetched_at FROM _tmp_fin"
            )
            self._conn.unregister("_tmp_fin")
        except Exception as exc:
            logger.error("upsert_financial failed: %s", exc)

    def get_financial(self, symbol: str, period_type: str) -> pd.DataFrame:
        try:
            return self._conn.execute(
                "SELECT period_key, item, value, source, fetched_at FROM financial_canonical "
                "WHERE symbol = ? AND period_type = ? ORDER BY period_key",
                [symbol.upper(), period_type],
            ).df()
        except Exception:
            return pd.DataFrame()

    # ─────────────────── Documents ───────────────────────────────────────────

    def upsert_document(self, doc: dict):
        cols = ["doc_id", "symbol", "year", "period", "doc_type", "title", "url",
                "local_path", "source", "size_bytes", "fetched_at"]
        row = {c: doc.get(c) for c in cols}
        row["fetched_at"] = row["fetched_at"] or datetime.now()
        try:
            self._conn.execute(
                f"INSERT OR REPLACE INTO documents ({', '.join(cols)}) VALUES ({', '.join(['?'] * len(cols))})",
                [row[c] for c in cols],
            )
        except Exception as exc:
            logger.error("upsert_document failed: %s", exc)

    def get_documents(self, symbol: str) -> pd.DataFrame:
        try:
            return self._conn.execute(
                "SELECT * FROM documents WHERE symbol = ? ORDER BY year DESC NULLS LAST, doc_type",
                [symbol.upper()],
            ).df()
        except Exception:
            return pd.DataFrame()

    # ─────────────────── News ────────────────────────────────────────────────

    def upsert_news(self, items: list):
        cols = ["news_id", "symbol", "title", "url", "source", "published_at", "sentiment", "summary", "fetched_at"]
        for it in items or []:
            try:
                row = [it.get(c) for c in cols]
                row[-1] = row[-1] or datetime.now()
                self._conn.execute(
                    f"INSERT OR IGNORE INTO news_items ({', '.join(cols)}) VALUES ({', '.join(['?'] * len(cols))})",
                    row,
                )
            except Exception as exc:
                logger.debug("upsert_news skip: %s", exc)

    def get_news(self, symbol: str = "", days: int = 30, limit: int = 200) -> pd.DataFrame:
        try:
            q = ("SELECT * FROM news_items WHERE COALESCE(published_at, fetched_at) >= "
                 "CURRENT_TIMESTAMP - (? * INTERVAL 1 DAY)")
            params: list = [days]
            if symbol:
                q += " AND symbol = ?"
                params.append(symbol.upper())
            q += " ORDER BY COALESCE(published_at, fetched_at) DESC LIMIT ?"
            params.append(limit)
            return self._conn.execute(q, params).df()
        except Exception:
            return pd.DataFrame()

    # ─────────────────── Watchlist & Alerts ──────────────────────────────────

    def add_watch(self, symbol: str, note: str = ""):
        try:
            self._conn.execute("INSERT OR REPLACE INTO watchlist (symbol, note, added_at) VALUES (?, ?, ?)",
                               [symbol.upper(), note, datetime.now()])
        except Exception as exc:
            logger.error("add_watch failed: %s", exc)

    def remove_watch(self, symbol: str):
        try:
            self._conn.execute("DELETE FROM watchlist WHERE symbol = ?", [symbol.upper()])
        except Exception as exc:
            logger.error("remove_watch failed: %s", exc)

    def get_watchlist(self) -> pd.DataFrame:
        try:
            return self._conn.execute("SELECT * FROM watchlist ORDER BY added_at").df()
        except Exception:
            return pd.DataFrame(columns=["symbol", "note", "added_at"])

    def add_alert(self, symbol: str, condition: str, threshold: float):
        try:
            self._conn.execute("INSERT INTO price_alerts (symbol, condition, threshold) VALUES (?, ?, ?)",
                               [symbol.upper(), condition, float(threshold)])
        except Exception as exc:
            logger.error("add_alert failed: %s", exc)

    def get_alerts(self, active_only: bool = False) -> pd.DataFrame:
        try:
            q = "SELECT * FROM price_alerts"
            if active_only:
                q += " WHERE active"
            return self._conn.execute(q + " ORDER BY created_at DESC").df()
        except Exception:
            return pd.DataFrame()

    def mark_alert_triggered(self, alert_id: int, price: float):
        try:
            self._conn.execute(
                "UPDATE price_alerts SET active = FALSE, triggered_at = ?, triggered_price = ? WHERE id = ?",
                [datetime.now(), float(price), int(alert_id)],
            )
        except Exception as exc:
            logger.error("mark_alert_triggered failed: %s", exc)

    def delete_alert(self, alert_id: int):
        try:
            self._conn.execute("DELETE FROM price_alerts WHERE id = ?", [int(alert_id)])
        except Exception as exc:
            logger.error("delete_alert failed: %s", exc)

    # ─────────────────── Update log ──────────────────────────────────────────

    def log_update(self, job: str, status: str, detail: str = ""):
        try:
            self._conn.execute("INSERT INTO update_log (job, status, detail, created_at) VALUES (?, ?, ?, ?)",
                               [job, status, detail[:4000], datetime.now()])
        except Exception as exc:
            logger.debug("log_update failed: %s", exc)

    def get_update_log(self, limit: int = 50) -> pd.DataFrame:
        try:
            return self._conn.execute("SELECT * FROM update_log ORDER BY created_at DESC LIMIT ?", [limit]).df()
        except Exception:
            return pd.DataFrame()
