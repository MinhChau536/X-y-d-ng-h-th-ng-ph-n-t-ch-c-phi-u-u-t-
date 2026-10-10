"""
Unit tests for DuckDB Database.
"""
import pytest
from data.database import Database


@pytest.fixture
def temp_db():
    db = Database(db_path=":memory:")
    yield db
    db.close()


def test_insert_and_get_prices(temp_db, sample_ohlcv_df):
    temp_db.upsert_price(sample_ohlcv_df)
    
    retrieved = temp_db.get_price("FPT")
    assert not retrieved.empty
    assert len(retrieved) == len(sample_ohlcv_df)
    assert "close" in retrieved.columns


def test_portfolio_crud(temp_db):
    temp_db.add_position("default", "FPT", quantity=1000, buy_price=95000.0, buy_date="2024-01-15")
    positions = temp_db.get_portfolio("default")
    assert len(positions) == 1
    assert positions.iloc[0]["symbol"] == "FPT"
    assert positions.iloc[0]["quantity"] == 1000
    
    pos_id = int(positions.iloc[0]["id"])
    temp_db.delete_position(pos_id)
    empty_positions = temp_db.get_portfolio("default")
    assert empty_positions.empty
