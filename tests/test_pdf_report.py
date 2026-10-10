"""
Unit test for PDFReportGenerator.
"""
from reports.pdf_generator import PDFReportGenerator


def test_pdf_report_generation():
    generator = PDFReportGenerator()
    mock_analysis = {
        "symbol": "FPT",
        "company_info": {
            "symbol": "FPT",
            "company_name": "Công ty Cổ phần FPT",
            "exchange": "HOSE",
            "industry": "Công nghệ thông tin",
        },
        "current_price": {
            "price": 105000.0,
            "change": 1500.0,
            "change_pct": 1.45,
        },
        "technical_score": {"score": 75, "rating": "Tích cực"},
        "opportunity_score": {
            "score": 78,
            "classification": {"label": "Tích cực", "color": "#69f0ae"},
            "coverage_pct": 100,
        },
        "signals": {
            "trend": {"name": "Tăng mạnh", "color": "#00e676"},
            "rsi": {"value": 58.5, "signal": "Tích cực"},
        },
    }
    
    pdf_bytes = generator.generate(mock_analysis, report_type="short")
    assert pdf_bytes is not None
    assert len(pdf_bytes) > 1000
    assert pdf_bytes.startswith(b"%PDF")
