"""
Global CSS for Stock Analytics Pro (Light and Dark themes with interactive hover micro-animations).
"""

COMMON_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800;900&display=swap');

/* ── Hide default Streamlit navigation on sidebar top-left ── */
[data-testid="stSidebarNav"],
ul[data-testid="stSidebarNavItems"],
div[data-testid="stSidebarNavSeparator"] {
    display: none !important;
    height: 0px !important;
    visibility: hidden !important;
    margin: 0 !important;
    padding: 0 !important;
}

html, body, [class*="css"] {
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
}

[data-testid="stMetricDelta"] svg { display: none; }

::-webkit-scrollbar { width: 7px; height: 7px; }
"""

LIGHT_CSS = COMMON_CSS + """
/* ==============================================================================
   LIGHT THEME (Sáng: Nền sáng tinh khôi, chữ tối đậm nét, độ tương phản cao)
   ============================================================================== */
.stApp {
    background: #f8fafc !important;
    color: #0f172a !important;
}

/* ── Streamlit Header / Top Bar Light ── */
header,
header[data-testid="stHeader"],
[data-testid="stAppHeader"],
.stAppHeader {
    background: #f8fafc !important;
    background-color: #f8fafc !important;
    border-bottom: 1px solid #e2e8f0 !important;
}
[data-testid="stToolbar"],
[data-testid="stHeaderActionElements"],
[data-testid="stStatusWidget"] {
    background: transparent !important;
}
[data-testid="stToolbar"] *,
header * {
    color: #475569 !important;
    fill: #475569 !important;
}
[data-testid="stDecoration"] {
    display: none !important;
}

/* ── Typography Light: Chữ tối nổi bật ── */
h1, h2, h3, h4, h5, h6 {
    color: #0f172a !important;
    font-weight: 800 !important;
    letter-spacing: -0.3px;
}
p, span, label {
    color: #334155 !important;
}

/* ── Metric Cards Light (Chữ tối đậm, hover nổi bật) ── */
[data-testid="stMetric"] {
    background: #ffffff !important;
    border: 1px solid #e2e8f0 !important;
    border-radius: 14px !important;
    padding: 14px 18px !important;
    box-shadow: 0 1px 4px rgba(0, 0, 0, 0.05) !important;
    transition: all 0.28s cubic-bezier(0.34, 1.56, 0.64, 1) !important;
    cursor: pointer;
}
[data-testid="stMetric"]:hover {
    transform: translateY(-5px) scale(1.015) !important;
    border-color: #0284c7 !important;
    box-shadow: 0 12px 28px -6px rgba(2, 132, 199, 0.22), 0 0 0 1.5px #0284c7 !important;
}
[data-testid="stMetricValue"] {
    color: #0f172a !important;
    font-weight: 800 !important;
    font-size: 30px !important;
    line-height: 1.2 !important;
}
[data-testid="stMetricLabel"] {
    color: #1e293b !important;
    font-weight: 700 !important;
    font-size: 14px !important;
}

/* ── Sidebar Light ── */
[data-testid="stSidebar"] {
    background: #ffffff !important;
    border-right: 1px solid #e2e8f0 !important;
}
[data-testid="stSidebar"] h1, [data-testid="stSidebar"] h2, [data-testid="stSidebar"] h3 {
    color: #0f172a !important;
}
[data-testid="stSidebar"] p, [data-testid="stSidebar"] span {
    color: #334155 !important;
}

/* ── Cards Light ── */
.metric-card {
    background: #ffffff !important;
    border: 1px solid #e2e8f0 !important;
    border-radius: 14px !important;
    padding: 16px 20px !important;
    margin-bottom: 14px !important;
    box-shadow: 0 1px 4px rgba(0, 0, 0, 0.05) !important;
    transition: all 0.28s cubic-bezier(0.34, 1.56, 0.64, 1) !important;
}
.metric-card:hover {
    transform: translateY(-4px) !important;
    border-color: #0284c7 !important;
    box-shadow: 0 12px 28px -6px rgba(2, 132, 199, 0.2) !important;
}

/* ── Page Header Light ── */
.page-header {
    background: #ffffff !important;
    border-radius: 14px !important;
    padding: 20px 24px !important;
    border: 1px solid #e2e8f0 !important;
    margin-bottom: 20px !important;
    box-shadow: 0 1px 4px rgba(0, 0, 0, 0.04) !important;
    transition: all 0.28s ease !important;
}
.page-header:hover {
    transform: translateY(-2px) !important;
    box-shadow: 0 8px 24px rgba(2, 132, 199, 0.12) !important;
    border-color: #bae6fd !important;
}
.page-header h1 {
    color: #0f172a !important;
}
.page-header p {
    color: #475569 !important;
}

/* ── Buttons Light (Hover effect) ── */
.stButton > button {
    background: linear-gradient(135deg, #0284c7, #2563eb) !important;
    color: #ffffff !important;
    border: none !important;
    border-radius: 10px !important;
    padding: 9px 22px !important;
    font-weight: 700 !important;
    font-size: 14px !important;
    transition: all 0.25s cubic-bezier(0.34, 1.56, 0.64, 1) !important;
    box-shadow: 0 2px 8px rgba(2, 132, 199, 0.25) !important;
}
.stButton > button:hover {
    transform: translateY(-2px) scale(1.02) !important;
    box-shadow: 0 8px 20px rgba(2, 132, 199, 0.4) !important;
    filter: brightness(1.08) !important;
}
.stButton > button:active {
    transform: translateY(0px) scale(0.98) !important;
}

/* ── Inputs & Selects Light ── */
.stTextInput input, .stSelectbox select, div[data-baseweb="select"] {
    background: #ffffff !important;
    border: 1px solid #cbd5e1 !important;
    color: #0f172a !important;
    border-radius: 10px !important;
    transition: all 0.2s ease !important;
}
.stTextInput input:hover, div[data-baseweb="select"]:hover {
    border-color: #0284c7 !important;
    box-shadow: 0 0 0 3px rgba(2, 132, 199, 0.12) !important;
}
.stTextInput input:focus {
    border-color: #0284c7 !important;
    box-shadow: 0 0 0 3px rgba(2, 132, 199, 0.2) !important;
}

/* ── Tabs Light ── */
.stTabs [data-baseweb="tab-list"] {
    background: #f1f5f9 !important;
    border-radius: 10px !important;
    padding: 5px !important;
    gap: 6px !important;
}
.stTabs [data-baseweb="tab"] {
    background: transparent !important;
    border-radius: 8px !important;
    color: #475569 !important;
    font-weight: 600 !important;
    transition: all 0.2s ease !important;
}
.stTabs [data-baseweb="tab"]:hover {
    color: #0284c7 !important;
    transform: translateY(-1px) !important;
}
.stTabs [aria-selected="true"] {
    background: #0284c7 !important;
    color: #ffffff !important;
    box-shadow: 0 2px 6px rgba(2, 132, 199, 0.3) !important;
}

/* ── DataFrames Light ── */
.stDataFrame {
    border: 1px solid #e2e8f0 !important;
    border-radius: 10px !important;
    background: #ffffff !important;
    transition: all 0.25s ease !important;
}
.stDataFrame:hover {
    border-color: #0284c7 !important;
    box-shadow: 0 6px 18px rgba(2, 132, 199, 0.1) !important;
}
[data-testid="stDataFrame"] thead tr th {
    background: #f1f5f9 !important;
    color: #1e293b !important;
    font-weight: 700 !important;
}

/* ── Radio buttons hover in Sidebar ── */
div[role="radiogroup"] label {
    transition: all 0.2s ease !important;
}
div[role="radiogroup"] label:hover {
    transform: translateX(3px) !important;
}

/* ── Numbers & Status Colors Light ── */
.positive { color: #15803d !important; font-weight: 700 !important; }
.negative { color: #dc2626 !important; font-weight: 700 !important; }
.status-ok { color: #15803d !important; font-weight: 700 !important; }
.status-error { color: #dc2626 !important; font-weight: 700 !important; }
.status-warning { color: #d97706 !important; font-weight: 700 !important; }

::-webkit-scrollbar-track { background: #f8fafc; }
::-webkit-scrollbar-thumb { background: #cbd5e1; border-radius: 4px; }
::-webkit-scrollbar-thumb:hover { background: #0284c7; }
</style>
"""

DARK_CSS = COMMON_CSS + """
/* ==============================================================================
   DARK THEME (Tối: Nền tối sang trọng, chữ sáng trắng nổi bật, tương phản cao)
   ============================================================================== */
.stApp {
    background: #0d1117 !important;
    color: #f0f6fc !important;
}

/* ── Streamlit Header / Top Bar Dark ── */
header,
header[data-testid="stHeader"],
[data-testid="stAppHeader"],
.stAppHeader {
    background: #0d1117 !important;
    background-color: #0d1117 !important;
    border-bottom: 1px solid #21262d !important;
}
[data-testid="stToolbar"],
[data-testid="stHeaderActionElements"],
[data-testid="stStatusWidget"] {
    background: transparent !important;
}
[data-testid="stToolbar"] *,
header * {
    color: #e6edf3 !important;
    fill: #e6edf3 !important;
}
[data-testid="stDecoration"] {
    display: none !important;
}

/* ── Typography Dark: Chữ sáng nổi bật ── */
h1, h2, h3, h4, h5, h6 {
    color: #ffffff !important;
    font-weight: 800 !important;
    letter-spacing: -0.3px;
}
p, span, label {
    color: #c9d1d9 !important;
}

/* ── Metric Cards Dark (Chữ sáng rực, hover nổi bật) ── */
[data-testid="stMetric"] {
    background: #161b22 !important;
    border: 1px solid #30363d !important;
    border-radius: 14px !important;
    padding: 14px 18px !important;
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.3) !important;
    transition: all 0.28s cubic-bezier(0.34, 1.56, 0.64, 1) !important;
    cursor: pointer;
}
[data-testid="stMetric"]:hover {
    transform: translateY(-5px) scale(1.015) !important;
    border-color: #58a6ff !important;
    box-shadow: 0 12px 28px -6px rgba(88, 166, 255, 0.32), 0 0 0 1.5px #58a6ff !important;
}
[data-testid="stMetricValue"] {
    color: #ffffff !important;
    font-weight: 800 !important;
    font-size: 30px !important;
    line-height: 1.2 !important;
    text-shadow: 0 2px 6px rgba(0, 0, 0, 0.5);
}
[data-testid="stMetricLabel"] {
    color: #f0f6fc !important;
    font-weight: 700 !important;
    font-size: 14px !important;
}

/* ── Sidebar Dark ── */
[data-testid="stSidebar"] {
    background: #090d13 !important;
    border-right: 1px solid #21262d !important;
}
[data-testid="stSidebar"] h1, [data-testid="stSidebar"] h2, [data-testid="stSidebar"] h3 {
    color: #ffffff !important;
}
[data-testid="stSidebar"] p, [data-testid="stSidebar"] span {
    color: #c9d1d9 !important;
}

/* ── Cards Dark ── */
.metric-card {
    background: #161b22 !important;
    border: 1px solid #30363d !important;
    border-radius: 14px !important;
    padding: 16px 20px !important;
    margin-bottom: 14px !important;
    transition: all 0.28s cubic-bezier(0.34, 1.56, 0.64, 1) !important;
}
.metric-card:hover {
    transform: translateY(-4px) !important;
    border-color: #58a6ff !important;
    box-shadow: 0 12px 28px -6px rgba(88, 166, 255, 0.25) !important;
}

/* ── Page Header Dark ── */
.page-header {
    background: linear-gradient(135deg, #161b22, #1c2128) !important;
    border-radius: 14px !important;
    padding: 20px 24px !important;
    border: 1px solid #30363d !important;
    margin-bottom: 20px !important;
    transition: all 0.28s ease !important;
}
.page-header:hover {
    transform: translateY(-2px) !important;
    box-shadow: 0 8px 24px rgba(88, 166, 255, 0.15) !important;
    border-color: #58a6ff !important;
}
.page-header h1 {
    color: #ffffff !important;
}
.page-header p {
    color: #8b949e !important;
}

/* ── Buttons Dark (Hover effect) ── */
.stButton > button {
    background: linear-gradient(135deg, #1f6feb, #238636) !important;
    color: #ffffff !important;
    border: none !important;
    border-radius: 10px !important;
    padding: 9px 22px !important;
    font-weight: 700 !important;
    font-size: 14px !important;
    transition: all 0.25s cubic-bezier(0.34, 1.56, 0.64, 1) !important;
    box-shadow: 0 2px 8px rgba(31, 111, 235, 0.3) !important;
}
.stButton > button:hover {
    transform: translateY(-2px) scale(1.02) !important;
    box-shadow: 0 8px 22px rgba(88, 166, 255, 0.45) !important;
    filter: brightness(1.12) !important;
}
.stButton > button:active {
    transform: translateY(0px) scale(0.98) !important;
}

/* ── Inputs & Selects Dark ── */
.stTextInput input, .stSelectbox select, div[data-baseweb="select"] {
    background: #161b22 !important;
    border: 1px solid #30363d !important;
    color: #ffffff !important;
    border-radius: 10px !important;
    transition: all 0.2s ease !important;
}
.stTextInput input:hover, div[data-baseweb="select"]:hover {
    border-color: #58a6ff !important;
    box-shadow: 0 0 0 3px rgba(88, 166, 255, 0.2) !important;
}
.stTextInput input:focus {
    border-color: #58a6ff !important;
    box-shadow: 0 0 0 3px rgba(88, 166, 255, 0.3) !important;
}

/* ── Tabs Dark ── */
.stTabs [data-baseweb="tab-list"] {
    background: #161b22 !important;
    border-radius: 10px !important;
    padding: 5px !important;
    gap: 6px !important;
}
.stTabs [data-baseweb="tab"] {
    background: transparent !important;
    border-radius: 8px !important;
    color: #8b949e !important;
    font-weight: 600 !important;
    transition: all 0.2s ease !important;
}
.stTabs [data-baseweb="tab"]:hover {
    color: #58a6ff !important;
    transform: translateY(-1px) !important;
}
.stTabs [aria-selected="true"] {
    background: #1f6feb !important;
    color: #ffffff !important;
    box-shadow: 0 2px 6px rgba(31, 111, 235, 0.4) !important;
}

/* ── DataFrames Dark ── */
.stDataFrame {
    border: 1px solid #30363d !important;
    border-radius: 10px !important;
    background: #161b22 !important;
    transition: all 0.25s ease !important;
}
.stDataFrame:hover {
    border-color: #58a6ff !important;
    box-shadow: 0 6px 18px rgba(88, 166, 255, 0.15) !important;
}
[data-testid="stDataFrame"] thead tr th {
    background: #21262d !important;
    color: #ffffff !important;
    font-weight: 700 !important;
}

/* ── Radio buttons hover in Sidebar ── */
div[role="radiogroup"] label {
    transition: all 0.2s ease !important;
}
div[role="radiogroup"] label:hover {
    transform: translateX(3px) !important;
}

/* ── Numbers & Status Colors Dark ── */
.positive { color: #00e676 !important; font-weight: 700 !important; }
.negative { color: #ff5252 !important; font-weight: 700 !important; }
.status-ok { color: #00e676 !important; font-weight: 700 !important; }
.status-error { color: #ff5252 !important; font-weight: 700 !important; }
.status-warning { color: #ffd740 !important; font-weight: 700 !important; }

::-webkit-scrollbar-track { background: #0d1117; }
::-webkit-scrollbar-thumb { background: #30363d; border-radius: 4px; }
::-webkit-scrollbar-thumb:hover { background: #58a6ff; }
</style>
"""


def load_css(theme: str = "light") -> str:
    """Return CSS styling corresponding to active theme."""
    if theme == "dark":
        return DARK_CSS
    return LIGHT_CSS


# Backward compatibility alias
CSS = LIGHT_CSS
