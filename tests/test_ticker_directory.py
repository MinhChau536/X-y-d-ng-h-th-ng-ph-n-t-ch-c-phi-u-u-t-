"""
Unit tests for data.ticker_directory module.
"""
from data.ticker_directory import (
    load_all_stocks,
    get_basket_names,
    get_tickers_for_basket,
    get_ticker_label,
    extract_symbol_from_label,
    find_option_for_symbol,
)


def test_load_all_stocks():
    stocks = load_all_stocks()
    assert len(stocks) >= 10
    symbols = [s["symbol"] for s in stocks]
    assert "FPT" in symbols
    assert "HPG" in symbols
    assert "VCB" in symbols


def test_baskets_and_sectors():
    baskets = get_basket_names()
    assert len(baskets) >= 5
    assert "⭐ VN30 (Blue-chips HSX)" in baskets
    assert "🏦 Ngân hàng" in baskets

    vn30 = get_tickers_for_basket("⭐ VN30 (Blue-chips HSX)")
    assert len(vn30) == 30
    assert "FPT" in vn30
    assert "HPG" in vn30

    banks = get_tickers_for_basket("🏦 Ngân hàng")
    assert "VCB" in banks
    assert "TCB" in banks


def test_label_and_symbol_extraction():
    fpt_label = get_ticker_label("FPT")
    assert fpt_label.startswith("FPT")
    assert extract_symbol_from_label(fpt_label) == "FPT"

    assert extract_symbol_from_label("DGC") == "DGC"
    assert extract_symbol_from_label("  vre  ") == "VRE"
    assert extract_symbol_from_label("MBB - MBBank (HSX)") == "MBB"


def test_find_option_for_symbol():
    options = ["FPT - FPT Corp (HSX)", "HPG - Hoa Phat (HSX)", "VCB - Vietcombank (HSX)"]
    found = find_option_for_symbol("HPG", options)
    assert found == "HPG - Hoa Phat (HSX)"

    assert find_option_for_symbol("UNKNOWN", options) is None
