"""
Global CSS for Stock Analytics Pro dark theme.
Inject with: st.markdown(load_css(), unsafe_allow_html=True)
"""

CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap');

/* ── Base ── */
html, body, [class*="css"] {
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
}
.stApp {
    background: #0d1117;
    color: #e6edf3;
}

/* ── Sidebar ── */
[data-testid="stSidebar"] {
    background: #010409;
    border-right: 1px solid #21262d;
}
[data-testid="stSidebar"] .stMarkdown {
    color: #e6edf3;
}

/* ── Cards ── */
.metric-card {
    background: #161b22;
    border: 1px solid #21262d;
    border-radius: 12px;
    padding: 16px 20px;
    margin-bottom: 12px;
    transition: border-color 0.2s;
}
.metric-card:hover { border-color: #2979ff; }

/* ── Metric deltas ── */
[data-testid="stMetricDelta"] svg { display: none; }

/* ── Buttons ── */
.stButton > button {
    background: linear-gradient(135deg, #1565c0, #2979ff);
    color: white;
    border: none;
    border-radius: 8px;
    padding: 8px 20px;
    font-weight: 600;
    font-size: 14px;
    transition: all 0.2s;
}
.stButton > button:hover {
    background: linear-gradient(135deg, #1976d2, #448aff);
    transform: translateY(-1px);
    box-shadow: 0 4px 12px rgba(41,121,255,0.3);
}

/* ── Inputs ── */
.stTextInput input, .stSelectbox select {
    background: #21262d !important;
    border: 1px solid #30363d !important;
    color: #e6edf3 !important;
    border-radius: 8px !important;
}
.stTextInput input:focus, .stSelectbox select:focus {
    border-color: #2979ff !important;
    box-shadow: 0 0 0 2px rgba(41,121,255,0.2) !important;
}

/* ── DataFrames ── */
.stDataFrame {
    border: 1px solid #21262d;
    border-radius: 8px;
    overflow: hidden;
}
[data-testid="stDataFrame"] thead tr th {
    background: #21262d !important;
    color: #8b949e !important;
    font-size: 11px !important;
    font-weight: 600 !important;
    text-transform: uppercase !important;
    letter-spacing: 0.5px;
}

/* ── Tabs ── */
.stTabs [data-baseweb="tab-list"] {
    background: #161b22;
    border-radius: 8px;
    padding: 4px;
    gap: 4px;
}
.stTabs [data-baseweb="tab"] {
    background: transparent;
    border-radius: 6px;
    color: #8b949e;
    font-weight: 500;
}
.stTabs [aria-selected="true"] {
    background: #2979ff !important;
    color: white !important;
}

/* ── Expander ── */
.streamlit-expanderHeader {
    background: #161b22 !important;
    border-radius: 8px;
    color: #e6edf3 !important;
}

/* ── Progress ── */
.stProgress > div > div {
    background: linear-gradient(90deg, #1565c0, #2979ff);
    border-radius: 4px;
}

/* ── Alert boxes ── */
.stAlert {
    border-radius: 8px;
    border-left-width: 4px;
}

/* ── Scrollbar ── */
::-webkit-scrollbar { width: 6px; height: 6px; }
::-webkit-scrollbar-track { background: #0d1117; }
::-webkit-scrollbar-thumb { background: #30363d; border-radius: 3px; }
::-webkit-scrollbar-thumb:hover { background: #2979ff; }

/* ── Status indicators ── */
.status-ok { color: #00e676; font-weight: 600; }
.status-error { color: #ff1744; font-weight: 600; }
.status-warning { color: #ffd740; font-weight: 600; }

/* ── Number colors ── */
.positive { color: #00e676 !important; }
.negative { color: #ff1744 !important; }

/* ── Header gradient ── */
.page-header {
    background: linear-gradient(135deg, #161b22, #21262d);
    border-radius: 12px;
    padding: 20px 24px;
    border: 1px solid #21262d;
    margin-bottom: 20px;
}
</style>
"""


def load_css() -> str:
    return CSS
