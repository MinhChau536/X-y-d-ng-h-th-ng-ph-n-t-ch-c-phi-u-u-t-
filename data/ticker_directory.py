"""
Comprehensive Stock Directory and Industry Baskets for Vietnam Equities.
Provides fast lookups, sector/index basket filters, and formatted labels
for all ~1,750+ listed stocks across HOSE, HNX, and UPCoM.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Optional

# Pre-defined Index & Sector Baskets (as in modern quant & report miners)
BASKETS: Dict[str, List[str]] = {
    "Tất cả (~1,750+ mã)": [],  # Filled dynamically from all listings
    "⭐ VN30 (Blue-chips HSX)": [
        "ACB", "BCM", "BID", "BVH", "CTG", "FPT", "GAS", "GVR", "HDB", "HPG",
        "MBB", "MSN", "MWG", "PLX", "POW", "SAB", "SHB", "SSB", "SSI", "STB",
        "TCB", "TPB", "VCB", "VHM", "VIB", "VIC", "VJC", "VNM", "VPB", "VRE"
    ],
    "⭐ HNX30 (Trụ cột HNX)": [
        "BVS", "CAP", "CEO", "DHT", "DTD", "HUT", "IDC", "IDV", "L14", "LAS",
        "MBS", "NBC", "NET", "NTP", "PBL", "PGS", "PLC", "PSD", "PVC", "PVS",
        "SHS", "SLS", "SZB", "THT", "TNG", "TVD", "VC3", "VCS", "VGS"
    ],
    "🏦 Ngân hàng": [
        "VCB", "BID", "CTG", "TCB", "MBB", "ACB", "VPB", "STB", "HDB", "SHB",
        "TPB", "VIB", "LPB", "MSB", "OCB", "EIB", "SSB", "NAB", "BVB", "BAB",
        "NVB", "PGB", "ABB", "KLB", "VAB", "SGB"
    ],
    "📈 Chứng khoán": [
        "SSI", "VND", "VCI", "HCM", "SHS", "MBS", "FTS", "BSI", "CTS", "VIX",
        "AGR", "ORS", "TVS", "VDS", "TCI", "SBS", "APS", "PSI", "IVS", "EVS",
        "APG", "VIG"
    ],
    "🏢 Bất động sản": [
        "VHM", "VIC", "VRE", "NVL", "KDH", "DIG", "DXG", "PDR", "KBC", "NLG",
        "CEO", "HDC", "DXS", "TCH", "IJC", "CRE", "SCR", "D2D", "SZC", "IDC",
        "NHA", "HQC", "LDG", "QCG", "KHG", "BCM"
    ],
    "🏗️ Thép & VLXD": [
        "HPG", "HSG", "NKG", "VGS", "TLH", "POM", "TVN", "SMC", "BCC", "HT1",
        "DHA", "KSB", "NNC", "VCS"
    ],
    "💻 Công nghệ & Viễn thông": [
        "FPT", "CMG", "FOX", "ELC", "CTR", "VGI", "SAM", "ICT", "ITD", "ONE", "SGT"
    ],
    "🛒 Bán lẻ & Tiêu dùng": [
        "MWG", "FRT", "DGW", "PNJ", "VNM", "MSN", "SAB", "KDC", "HAG", "DBC",
        "BAF", "MCH", "QNS", "VHC", "ANV", "IDI", "FMC"
    ],
    "⚡ Dầu khí & Năng lượng": [
        "GAS", "PLX", "PVD", "PVS", "BSR", "PVT", "POW", "REE", "GEG", "HDG",
        "PC1", "NT2", "PGV", "TV2", "VSH", "SBA"
    ],
    "🧪 Hóa chất & Phân bón": [
        "DGC", "DCM", "DPM", "BFC", "CSV", "LAS", "DDV", "PHR", "DPR", "DRI", "GVR"
    ],
    "🚢 Cảng biển & Logistics": [
        "GMD", "HAH", "VSC", "PVT", "VOS", "TCL", "DVP", "TMS", "SGP", "MVN", "PHP"
    ],
    "🧵 Dệt may & Thủy sản": [
        "TNG", "MSH", "TCM", "STK", "VGT", "GIL", "VHC", "ANV", "IDI", "FMC", "CMX"
    ],
}

_ALL_STOCKS_CACHE: Optional[List[Dict[str, str]]] = None
_SYMBOL_MAP_CACHE: Optional[Dict[str, Dict[str, str]]] = None


def load_all_stocks() -> List[Dict[str, str]]:
    """Loads all listed stocks from local persistent cache or default."""
    global _ALL_STOCKS_CACHE, _SYMBOL_MAP_CACHE
    if _ALL_STOCKS_CACHE is not None:
        return _ALL_STOCKS_CACHE

    json_file = Path(__file__).resolve().parent / "listed_stocks.json"
    stocks: List[Dict[str, str]] = []
    if json_file.exists():
        try:
            with open(json_file, "r", encoding="utf-8") as f:
                stocks = json.load(f)
        except Exception:
            stocks = []

    if not stocks:
        # Fallback to popular tickers if file cannot be read
        stocks = [
            {"symbol": "FPT", "exchange": "HSX", "organ_short_name": "Tập đoàn FPT", "organ_name": "Công ty Cổ phần FPT"},
            {"symbol": "HPG", "exchange": "HSX", "organ_short_name": "Tập đoàn Hòa Phát", "organ_name": "Công ty Cổ phần Tập đoàn Hòa Phát"},
            {"symbol": "VCB", "exchange": "HSX", "organ_short_name": "Vietcombank", "organ_name": "Ngân hàng TMCP Ngoại thương Việt Nam"},
            {"symbol": "SSI", "exchange": "HSX", "organ_short_name": "Chứng khoán SSI", "organ_name": "Công ty Cổ phần Chứng khoán SSI"},
            {"symbol": "MWG", "exchange": "HSX", "organ_short_name": "Thế Giới Di Động", "organ_name": "Công ty Cổ phần Đầu tư Thế Giới Di Động"},
            {"symbol": "TCB", "exchange": "HSX", "organ_short_name": "Techcombank", "organ_name": "Ngân hàng TMCP Kỹ Thương Việt Nam"},
            {"symbol": "VHM", "exchange": "HSX", "organ_short_name": "Vinhomes", "organ_name": "Công ty Cổ phần Vinhomes"},
            {"symbol": "VNM", "exchange": "HSX", "organ_short_name": "Vinamilk", "organ_name": "Công ty Cổ phần Sữa Việt Nam"},
            {"symbol": "MBB", "exchange": "HSX", "organ_short_name": "MBBank", "organ_name": "Ngân hàng TMCP Quân Đội"},
            {"symbol": "STB", "exchange": "HSX", "organ_short_name": "Sacombank", "organ_name": "Ngân hàng TMCP Sài Gòn Thương Tín"},
        ]

    _ALL_STOCKS_CACHE = stocks
    _SYMBOL_MAP_CACHE = {s["symbol"].upper(): s for s in stocks}
    return _ALL_STOCKS_CACHE


def get_symbol_map() -> Dict[str, Dict[str, str]]:
    """Returns map of symbol -> stock metadata."""
    if _SYMBOL_MAP_CACHE is None:
        load_all_stocks()
    return _SYMBOL_MAP_CACHE or {}


def get_basket_names() -> List[str]:
    """Returns list of basket / sector category names."""
    return list(BASKETS.keys())


def get_tickers_for_basket(basket_name: str) -> List[str]:
    """Returns list of symbols matching the selected basket/category."""
    stocks = load_all_stocks()
    if basket_name == "Tất cả (~1,750+ mã)":
        return [s["symbol"] for s in stocks]
    
    basket_symbols = BASKETS.get(basket_name, [])
    # Return matched symbols in order
    return basket_symbols


def get_ticker_label(symbol: str) -> str:
    """Formats symbol as display string: 'SYMBOL - Tên công ty (Sàn)'."""
    symbol_upper = symbol.strip().upper()
    s_map = get_symbol_map()
    meta = s_map.get(symbol_upper)
    if meta:
        raw_name = meta.get("organ_short_name") or meta.get("organ_name") or ""
        name = str(raw_name).strip() if raw_name is not None else ""
        if name.lower() == "nan":
            name = ""
        raw_exch = meta.get("exchange") or ""
        exch = str(raw_exch).strip() if raw_exch is not None else ""
        if exch.lower() == "nan":
            exch = ""
        # Shorten very long names if needed
        if len(name) > 32:
            name = name[:30] + "..."
        if name and exch:
            return f"{symbol_upper} - {name} ({exch})"
        elif name:
            return f"{symbol_upper} - {name}"
        return f"{symbol_upper} ({exch})" if exch else symbol_upper
    return symbol_upper


def extract_symbol_from_label(label: str) -> str:
    """Extracts raw ticker symbol from formatted label or text input."""
    if not label:
        return "FPT"
    clean = label.strip()
    if " - " in clean:
        return clean.split(" - ")[0].strip().upper()
    if " (" in clean:
        return clean.split(" (")[0].strip().upper()
    return clean.upper()


def get_formatted_options(basket_name: str = "Tất cả (~1,750+ mã)") -> List[str]:
    """Returns formatted display options for a given basket."""
    symbols = get_tickers_for_basket(basket_name)
    return [get_ticker_label(s) for s in symbols]


def find_option_for_symbol(symbol: str, options: List[str]) -> Optional[str]:
    """Finds matching option string in options list for a given symbol."""
    sym = symbol.strip().upper()
    for opt in options:
        if opt == sym or opt.startswith(f"{sym} ") or opt.startswith(f"{sym}-"):
            return opt
    return None
