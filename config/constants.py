"""
Application-wide constants for Stock Analytics Pro.
"""
from typing import Dict, List

# ─────────────────────────── Exchanges ──────────────────────────────────────
EXCHANGES = ["HOSE", "HNX", "UPCOM"]

# ─────────────────────────── Market Indices ──────────────────────────────────
MARKET_INDICES = {
    "VNINDEX": "VN-Index",
    "VN30": "VN30",
    "HNXINDEX": "HNX-Index",
    "UPCOMINDEX": "UPCoM-Index",
}

# ─────────────────────────── Sectors ─────────────────────────────────────────
SECTORS = [
    "Ngân hàng",
    "Bất động sản",
    "Công nghệ thông tin",
    "Công nghiệp",
    "Vật liệu cơ bản",
    "Hàng tiêu dùng",
    "Dịch vụ tiêu dùng",
    "Năng lượng",
    "Y tế",
    "Dịch vụ tài chính",
    "Bảo hiểm",
    "Viễn thông",
    "Tiện ích công cộng",
    "Nông nghiệp",
    "Hàng không - Vận tải",
]

# ─────────────────────────── Intervals ───────────────────────────────────────
INTERVALS = {
    "1m": "1 phút",
    "5m": "5 phút",
    "15m": "15 phút",
    "30m": "30 phút",
    "1H": "1 giờ",
    "1D": "1 ngày",
    "1W": "1 tuần",
    "1M": "1 tháng",
}

DNSE_INTERVAL_MAP = {
    "1D": "1",
    "1W": "W",
    "1M": "M",
    "1H": "60",
    "30m": "30",
    "15m": "15",
    "5m": "5",
    "1m": "1",
}

# ─────────────────────────── Technical Indicators ────────────────────────────
SMA_PERIODS = [10, 20, 50, 100, 200]
EMA_PERIODS = [12, 26]
RSI_PERIOD = 14
MACD_FAST = 12
MACD_SLOW = 26
MACD_SIGNAL = 9
BB_PERIOD = 20
BB_STD = 2
ATR_PERIOD = 14
ADX_PERIOD = 14
MFI_PERIOD = 14
CMF_PERIOD = 20
ROC_PERIOD = 10

# ─────────────────────────── Scoring Weights ─────────────────────────────────
DEFAULT_SCORE_WEIGHTS = {
    "technical": 25,
    "momentum": 20,
    "fundamental": 25,
    "valuation": 20,
    "risk": 10,
}

SCORE_CATEGORIES = {
    (80, 100): ("Cơ hội nổi bật", "#00e676", "🌟"),
    (65, 79): ("Tích cực", "#69f0ae", "✅"),
    (50, 64): ("Trung tính", "#ffd740", "⚖️"),
    (35, 49): ("Thận trọng", "#ff8f00", "⚠️"),
    (0, 34): ("Rủi ro cao", "#ff1744", "🚨"),
}

# ─────────────────────────── Fundamental Thresholds ──────────────────────────
FUNDAMENTAL_THRESHOLDS = {
    "roe_excellent": 20,
    "roe_good": 15,
    "roe_fair": 10,
    "roa_excellent": 10,
    "roa_good": 7,
    "roa_fair": 3,
    "pe_overvalued": 30,
    "pe_fair": 20,
    "pe_cheap": 12,
    "pb_overvalued": 3,
    "pb_fair": 1.5,
    "pb_cheap": 1.0,
    "debt_equity_high": 2.0,
    "net_margin_excellent": 20,
    "net_margin_good": 10,
    "net_margin_fair": 5,
}

# ─────────────────────────── RSI Zones ───────────────────────────────────────
RSI_OVERBOUGHT = 70
RSI_OVERSOLD = 30
RSI_NEUTRAL_HIGH = 60
RSI_NEUTRAL_LOW = 40

# ─────────────────────────── Colors ─────────────────────────────────────────
COLOR_BULLISH = "#00e676"
COLOR_BEARISH = "#ff1744"
COLOR_NEUTRAL = "#90a4ae"
COLOR_BG_DARK = "#0a0e1a"
COLOR_BG_CARD = "#111827"
COLOR_ACCENT = "#2979ff"
COLOR_TEXT = "#e2e8f0"
COLOR_TEXT_SECONDARY = "#94a3b8"

PLOTLY_TEMPLATE = "plotly_dark"

# ─────────────────────────── Date formats ────────────────────────────────────
DATE_FORMAT = "%Y-%m-%d"
DATETIME_FORMAT = "%Y-%m-%d %H:%M:%S"
DISPLAY_DATE_FORMAT = "%d/%m/%Y"
DISPLAY_DATETIME_FORMAT = "%d/%m/%Y %H:%M"

# ─────────────────────────── Time Ranges ─────────────────────────────────────
TIME_RANGES = {
    "3T": ("3 tháng", 90),
    "6T": ("6 tháng", 180),
    "1N": ("1 năm", 365),
    "3N": ("3 năm", 1095),
    "5N": ("5 năm", 1825),
    "TT": ("Tùy chỉnh", 0),
}

# ─────────────────────────── Currency ────────────────────────────────────────
CURRENCY = "VND"
PRICE_UNIT = 1  # Already in VND
VOLUME_UNIT = 1  # In shares

# ─────────────────────────── Data Schema ─────────────────────────────────────
PRICE_SCHEMA_COLUMNS = [
    "symbol", "timestamp", "open", "high", "low", "close",
    "volume", "value", "source", "interval", "adjusted", "fetched_at",
]

FINANCIAL_SCHEMA_COLUMNS = [
    "symbol", "period", "year", "quarter", "report_date",
    "currency", "report_type", "source", "fetched_at",
]
