"""
Abstract base class for all data providers.
"""
from abc import ABC, abstractmethod
from typing import Optional, Dict, Any
import pandas as pd
from datetime import datetime


class BaseProvider(ABC):
    """Abstract base data provider."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Provider name."""
        pass

    @property
    @abstractmethod
    def is_available(self) -> bool:
        """Check if provider is currently available."""
        pass

    @abstractmethod
    def get_price_history(
        self,
        symbol: str,
        start_date: str,
        end_date: str,
        interval: str = "1D",
    ) -> pd.DataFrame:
        """Get OHLCV price history."""
        pass

    @abstractmethod
    def get_current_price(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Get latest price data."""
        pass

    def validate_symbol(self, symbol: str) -> str:
        """Normalize and validate stock symbol."""
        return symbol.upper().strip()

    def health_check(self) -> Dict[str, Any]:
        """Return provider health status."""
        return {
            "provider": self.name,
            "available": self.is_available,
            "timestamp": datetime.now().isoformat(),
        }
