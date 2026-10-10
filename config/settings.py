"""
Global settings and configuration loader.
"""
import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env file
BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


class Settings:
    """Application settings loaded from environment variables."""

    # Base paths
    BASE_DIR: Path = BASE_DIR
    DATA_DIR: Path = BASE_DIR / "data"
    CACHE_DIR: Path = Path(os.getenv("CACHE_DIR", str(BASE_DIR / "data" / "cache")))
    REPORTS_DIR: Path = Path(os.getenv("REPORTS_DIR", str(BASE_DIR / "reports" / "output")))
    ASSETS_DIR: Path = BASE_DIR / "assets"
    DOCUMENTS_DIR: Path = Path(os.getenv("DOCUMENTS_DIR", str(BASE_DIR / "data" / "documents")))

    # Database
    DB_PATH: str = os.getenv("DB_PATH", str(BASE_DIR / "data" / "stock_analytics.duckdb"))

    # DNSE API
    _raw_dnse_url = os.getenv("DNSE_BASE_URL", "").strip()
    DNSE_BASE_URL: str = (
        _raw_dnse_url
        if _raw_dnse_url.startswith(("http://", "https://")) and len(_raw_dnse_url) > 10
        else "https://api.dnse.com.vn"
    )
    DNSE_USERNAME: str = os.getenv("DNSE_USERNAME", "").strip()
    DNSE_PASSWORD: str = os.getenv("DNSE_PASSWORD", "").strip()
    DNSE_TOKEN: str = (os.getenv("DNSE_TOKEN", "") or os.getenv("DNSE_API_KEY", "")).strip()

    # Vnstock
    VNSTOCK_SOURCE: str = os.getenv("VNSTOCK_SOURCE", "VCI").strip()
    VNSTOCK_API_KEY: str = os.getenv("VNSTOCK_API_KEY", "").strip()

    # ── Chiến lược nguồn dữ liệu ──
    # Giá: N ngày gần nhất lấy từ DNSE, phần trước đó lấy từ vnstock / Vietstock
    DNSE_RECENT_DAYS: int = int(os.getenv("DNSE_RECENT_DAYS", "365"))
    # Thứ tự ưu tiên nguồn giá lịch sử (phần cũ hơn DNSE_RECENT_DAYS)
    PRICE_HISTORY_SOURCES: list = [
        s.strip().lower() for s in os.getenv("PRICE_HISTORY_SOURCES", "vnstock_vci,vnstock_kbs,vnstock_msn,vietstock").split(",")
        if s.strip()
    ]
    # Thứ tự ưu tiên nguồn BCTC (nguồn sau bù phần nguồn trước thiếu)
    FINANCIAL_SOURCES: list = [
        s.strip().lower() for s in os.getenv("FINANCIAL_SOURCES", "vnstock_vci,vnstock_kbs,vietstock,pdf").split(",")
        if s.strip()
    ]
    # Thứ tự ưu tiên nguồn tài liệu PDF (BCTN / BCTC)
    DOCUMENT_SOURCES: list = [
        s.strip().lower() for s in os.getenv("DOCUMENT_SOURCES", "vietstock,cafef").split(",") if s.strip()
    ]

    # App settings
    APP_ENV: str = os.getenv("APP_ENV", "development")
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")

    # Cache TTL (seconds)
    CACHE_TTL_PRICE: int = int(os.getenv("CACHE_TTL_PRICE", "300"))
    CACHE_TTL_FINANCIAL: int = int(os.getenv("CACHE_TTL_FINANCIAL", "3600"))
    CACHE_TTL_MARKET: int = int(os.getenv("CACHE_TTL_MARKET", "60"))
    CACHE_TTL_NEWS: int = int(os.getenv("CACHE_TTL_NEWS", "1800"))
    CACHE_TTL_DOCUMENTS: int = int(os.getenv("CACHE_TTL_DOCUMENTS", "86400"))

    # API settings
    REQUEST_TIMEOUT: int = 30
    MAX_RETRIES: int = 3
    RETRY_BACKOFF: float = 1.5

    # Trading
    DEFAULT_TRANSACTION_FEE: float = 0.0015  # 0.15%
    DEFAULT_SLIPPAGE: float = 0.001  # 0.1%

    # Analysis defaults
    DEFAULT_LOOKBACK_DAYS: int = 365
    MIN_DATA_POINTS: int = 30

    @classmethod
    def ensure_dirs(cls):
        """Create necessary directories if they don't exist."""
        cls.DATA_DIR.mkdir(parents=True, exist_ok=True)
        cls.CACHE_DIR.mkdir(parents=True, exist_ok=True)
        cls.REPORTS_DIR.mkdir(parents=True, exist_ok=True)
        cls.DOCUMENTS_DIR.mkdir(parents=True, exist_ok=True)
        (cls.BASE_DIR / "reports" / "templates").mkdir(parents=True, exist_ok=True)


settings = Settings()
settings.ensure_dirs()
