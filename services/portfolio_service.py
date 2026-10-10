"""
PortfolioService – manages user portfolio and performance tracking.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

import pandas as pd

from services.stock_service import get_repo

logger = logging.getLogger(__name__)



class PortfolioService:
    """Portfolio management and P&L calculation."""

    def get_portfolio(self, name: str = "default") -> pd.DataFrame:
        return get_repo().get_portfolio(name)

    def add_position(
        self, symbol: str, quantity: float, buy_price: float,
        buy_date: str = "", fee_pct: float = 0.0015,
        notes: str = "", portfolio_name: str = "default"
    ):
        get_repo().add_position(portfolio_name, symbol, quantity, buy_price, buy_date, fee_pct, notes)

    def delete_position(self, position_id: int):
        get_repo().delete_position(position_id)

    def get_portfolio_with_pnl(self, portfolio_name: str = "default") -> pd.DataFrame:
        """Return portfolio positions with current prices and P&L."""
        portfolio = self.get_portfolio(portfolio_name)
        if portfolio.empty:
            return portfolio

        rows = []
        for _, row in portfolio.iterrows():
            symbol = str(row["symbol"])
            qty = float(row["quantity"])
            buy_price = float(row["buy_price"])
            fee_pct = float(row.get("fee_pct", 0.0015))

            # Get current price
            current_data = get_repo().get_current_price(symbol)
            current_price = current_data.get("price", 0) if current_data else 0

            cost_basis = buy_price * qty * (1 + fee_pct)
            current_value = current_price * qty
            unrealized_pnl = current_value - cost_basis
            unrealized_pct = unrealized_pnl / cost_basis * 100 if cost_basis else 0

            rows.append({
                "id": row.get("id"),
                "symbol": symbol,
                "quantity": qty,
                "buy_price": buy_price,
                "buy_date": str(row.get("buy_date", ""))[:10],
                "current_price": current_price,
                "cost_basis": round(cost_basis, 0),
                "current_value": round(current_value, 0),
                "unrealized_pnl": round(unrealized_pnl, 0),
                "unrealized_pct": round(unrealized_pct, 2),
                "notes": row.get("notes", ""),
            })

        return pd.DataFrame(rows)

    def get_portfolio_summary(self, portfolio_name: str = "default") -> Dict[str, Any]:
        """Return summary stats for the portfolio."""
        df = self.get_portfolio_with_pnl(portfolio_name)
        if df.empty:
            return {"empty": True}

        total_cost = df["cost_basis"].sum()
        total_value = df["current_value"].sum()
        total_pnl = df["unrealized_pnl"].sum()
        total_pct = total_pnl / total_cost * 100 if total_cost else 0

        # Weight by current value
        df["weight"] = df["current_value"] / total_value * 100 if total_value else 0

        return {
            "total_cost": round(total_cost, 0),
            "total_value": round(total_value, 0),
            "total_pnl": round(total_pnl, 0),
            "total_pct": round(total_pct, 2),
            "n_positions": len(df),
            "positions": df,
        }
