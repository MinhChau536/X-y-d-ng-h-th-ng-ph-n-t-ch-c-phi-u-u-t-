"""
Bộ tính chỉ số tài chính TỪ BÁO CÁO TÀI CHÍNH đã chuẩn hóa (không phụ thuộc bảng
chỉ số dựng sẵn của nhà cung cấp dữ liệu).

Đầu vào: bảng rộng canonical (index = khóa kỳ năm*10+quý, cột = chỉ tiêu chuẩn, VND).

Quy ước:
  - Kỳ NĂM: chỉ tiêu dòng (doanh thu, lợi nhuận, dòng tiền) dùng số của năm.
  - Kỳ QUÝ: chỉ tiêu dòng dùng TTM (tổng 4 quý liên tiếp gần nhất) khi tính tỷ suất
    sinh lời/vòng quay/định giá; bảng kết quả vẫn có số từng quý.
  - Chỉ tiêu số dư (tài sản, vốn…) dùng BÌNH QUÂN đầu kỳ – cuối kỳ cho các tỷ số
    dạng dòng/số dư (ROE, ROA, vòng quay…). Đầu kỳ = kỳ trước (năm) hoặc cùng kỳ năm
    trước (quý, khớp với TTM).
  - Phần trăm lưu dạng số % (15.2 nghĩa là 15,2%). Thiếu dữ liệu → NaN, không gán giả định.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

from analytics.period_utils import key_to_label

PAR_VALUE = 10_000  # mệnh giá cổ phiếu VN (đồng) – dùng ước tính số CP khi thiếu dữ liệu

# key: (nhãn, nhóm, định dạng, cao hơn là tốt?)
RATIO_META: Dict[str, tuple] = {
    # Khả năng sinh lời
    "gross_margin": ("Biên lợi nhuận gộp", "Khả năng sinh lời", "%", True),
    "operating_margin": ("Biên lợi nhuận HĐKD", "Khả năng sinh lời", "%", True),
    "ebitda_margin": ("Biên EBITDA", "Khả năng sinh lời", "%", True),
    "net_margin": ("Biên lợi nhuận ròng", "Khả năng sinh lời", "%", True),
    "roe": ("ROE", "Khả năng sinh lời", "%", True),
    "roa": ("ROA", "Khả năng sinh lời", "%", True),
    "roic": ("ROIC", "Khả năng sinh lời", "%", True),
    # Thanh khoản
    "current_ratio": ("Thanh toán hiện hành", "Thanh khoản", "x", True),
    "quick_ratio": ("Thanh toán nhanh", "Thanh khoản", "x", True),
    "cash_ratio": ("Thanh toán tiền mặt", "Thanh khoản", "x", True),
    # Đòn bẩy
    "debt_to_equity": ("Nợ vay / VCSH", "Cơ cấu vốn", "x", False),
    "liabilities_to_equity": ("Nợ phải trả / VCSH", "Cơ cấu vốn", "x", False),
    "liabilities_to_assets": ("Nợ phải trả / Tổng tài sản", "Cơ cấu vốn", "%", False),
    "net_debt_to_ebitda": ("Nợ vay ròng / EBITDA", "Cơ cấu vốn", "x", False),
    "interest_coverage": ("Khả năng trả lãi (EBIT / lãi vay)", "Cơ cấu vốn", "x", True),
    "equity_multiplier": ("Đòn bẩy tài chính (TTS / VCSH)", "Cơ cấu vốn", "x", None),
    # Hiệu quả hoạt động
    "asset_turnover": ("Vòng quay tổng tài sản", "Hiệu quả hoạt động", "x", True),
    "inventory_turnover": ("Vòng quay hàng tồn kho", "Hiệu quả hoạt động", "x", True),
    "dio": ("Số ngày tồn kho", "Hiệu quả hoạt động", "days", False),
    "dso": ("Số ngày thu tiền", "Hiệu quả hoạt động", "days", False),
    "dpo": ("Số ngày trả tiền", "Hiệu quả hoạt động", "days", None),
    "ccc": ("Chu kỳ tiền mặt", "Hiệu quả hoạt động", "days", False),
    # Tăng trưởng
    "revenue_growth": ("Tăng trưởng doanh thu (YoY)", "Tăng trưởng", "%", True),
    "net_income_growth": ("Tăng trưởng LNST (YoY)", "Tăng trưởng", "%", True),
    "eps_growth": ("Tăng trưởng EPS (YoY)", "Tăng trưởng", "%", True),
    "equity_growth": ("Tăng trưởng VCSH (YoY)", "Tăng trưởng", "%", True),
    "assets_growth": ("Tăng trưởng tổng tài sản (YoY)", "Tăng trưởng", "%", None),
    # Dòng tiền
    "fcf": ("Dòng tiền tự do (FCF)", "Dòng tiền", "vnd", True),
    "cfo_to_net_income": ("CFO / LNST", "Dòng tiền", "x", True),
    "fcf_margin": ("Biên FCF", "Dòng tiền", "%", True),
    "capex_to_revenue": ("Capex / Doanh thu", "Dòng tiền", "%", None),
    "dividend_payout": ("Tỷ lệ chi trả cổ tức", "Dòng tiền", "%", None),
    # Trên mỗi cổ phiếu
    "eps": ("EPS (tính từ BCTC)", "Trên mỗi cổ phiếu", "vnd", True),
    "bvps": ("Giá trị sổ sách / CP", "Trên mỗi cổ phiếu", "vnd", True),
    "dps": ("Cổ tức tiền mặt / CP", "Trên mỗi cổ phiếu", "vnd", True),
    # Ngân hàng
    "loan_to_deposit": ("Cho vay / Tiền gửi (LDR)", "Ngân hàng", "%", None),
    "equity_to_assets": ("VCSH / Tổng tài sản", "Ngân hàng", "%", True),
    "provision_to_income": ("Chi phí dự phòng / TN hoạt động", "Ngân hàng", "%", False),
}

VALUATION_META: Dict[str, tuple] = {
    "pe": ("P/E", "x"), "pb": ("P/B", "x"), "ps": ("P/S", "x"), "ev_ebitda": ("EV/EBITDA", "x"),
    "earnings_yield": ("Lợi suất lợi nhuận (E/P)", "%"), "dividend_yield": ("Tỷ suất cổ tức", "%"),
    "market_cap": ("Vốn hóa", "vnd"), "enterprise_value": ("Giá trị doanh nghiệp (EV)", "vnd"),
}


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _col(df: pd.DataFrame, name: str) -> pd.Series:
    return df[name].astype(float) if name in df.columns else pd.Series(np.nan, index=df.index, dtype=float)


def _div(a, b, pct: bool = False):
    with np.errstate(divide="ignore", invalid="ignore"):
        b = b.where(b != 0) if isinstance(b, pd.Series) else (np.nan if b == 0 else b)
        out = a / b
    return out * 100 if pct else out


def _lag(s: pd.Series, period: str) -> pd.Series:
    """Giá trị kỳ so sánh: năm trước (kỳ năm) hoặc cùng quý năm trước (kỳ quý), khớp theo khóa kỳ."""
    shifted = s.copy()
    shifted.index = shifted.index + 10      # key+10 = cùng kỳ năm sau → dời về
    return shifted.reindex(s.index)


def _ttm(s: pd.Series) -> pd.Series:
    """Tổng 4 quý liên tiếp (yêu cầu đủ 4 quý liền nhau theo khóa kỳ)."""
    out = pd.Series(np.nan, index=s.index, dtype=float)
    idx = list(s.index)
    for k in idx:
        y, q = divmod(int(k), 10)
        if not 1 <= q <= 4:
            continue
        keys = []
        yy, qq = y, q
        for _ in range(4):
            keys.append(yy * 10 + qq)
            qq -= 1
            if qq == 0:
                yy, qq = yy - 1, 4
        if all(kk in s.index and pd.notna(s.loc[kk]) for kk in keys):
            out.loc[k] = float(sum(s.loc[kk] for kk in keys))
    return out


def detect_period(wide: pd.DataFrame) -> str:
    if wide.empty:
        return "year"
    qs = (np.asarray(wide.index, dtype=int) % 10)
    return "quarter" if (qs > 0).mean() > 0.5 else "year"


def is_bank(wide: pd.DataFrame) -> bool:
    return any(c in wide.columns and wide[c].notna().any() for c in ("customer_deposits", "net_interest_income"))


def shares_series(wide: pd.DataFrame) -> pd.Series:
    sh = _col(wide, "shares_outstanding")
    est = _col(wide, "charter_capital") / PAR_VALUE
    return sh.where(sh > 0, est)


# ─────────────────────────────────────────────────────────────────────────────
# Main ratio computation
# ─────────────────────────────────────────────────────────────────────────────

def compute_ratios(wide: pd.DataFrame, period: Optional[str] = None) -> pd.DataFrame:
    """Bảng chỉ số theo từng kỳ (index = khóa kỳ, cột = khóa trong RATIO_META)."""
    if wide is None or wide.empty:
        return pd.DataFrame()
    wide = wide.sort_index()
    period = period or detect_period(wide)
    bank = is_bank(wide)

    flow = (lambda s: _ttm(s)) if period == "quarter" else (lambda s: s)
    avg = lambda s: pd.concat([s, _lag(s, period)], axis=1).mean(axis=1, skipna=False)  # noqa: E731

    rev_raw = _col(wide, "total_operating_income") if bank and "revenue" not in wide.columns else _col(wide, "revenue")
    rev = flow(rev_raw)
    cogs = flow(_col(wide, "cogs").abs())
    gp = flow(_col(wide, "gross_profit"))
    gp = gp.where(gp.notna(), rev - cogs)
    op = flow(_col(wide, "operating_profit"))
    pbt = flow(_col(wide, "profit_before_tax"))
    ni = flow(_col(wide, "net_income"))
    ni_parent = flow(_col(wide, "net_income_parent"))
    ni_parent = ni_parent.where(ni_parent.notna(), ni)
    ni = ni.where(ni.notna(), ni_parent)
    interest = flow(_col(wide, "interest_expense").abs())
    dep = flow(_col(wide, "depreciation").abs())
    tax = flow(_col(wide, "income_tax").abs())
    cfo = flow(_col(wide, "cfo"))
    capex = flow(_col(wide, "capex").abs())
    div_paid = flow(_col(wide, "dividends_paid").abs())

    ta, eq, tl = _col(wide, "total_assets"), _col(wide, "equity"), _col(wide, "total_liabilities")
    tl = tl.where(tl.notna(), ta - eq)
    ca, cl = _col(wide, "current_assets"), _col(wide, "current_liabilities")
    inv, recv, pay = _col(wide, "inventory"), _col(wide, "receivables"), _col(wide, "payables")
    cash = _col(wide, "cash")
    sti = _col(wide, "short_term_investments").fillna(0)
    std, ltd = _col(wide, "short_term_debt"), _col(wide, "long_term_debt")
    debt = (std.fillna(0) + ltd.fillna(0)).where(std.notna() | ltd.notna())   # NaN nếu không có số liệu vay
    minority = _col(wide, "minority_interest").fillna(0)
    eq_parent = eq - minority

    ebit = pbt + interest.fillna(0)
    ebitda = ebit + dep
    tax_rate = _div(tax, pbt).clip(0, 0.5).fillna(0.2)

    r = pd.DataFrame(index=wide.index)
    r["gross_margin"] = _div(gp, rev, pct=True) if not bank else np.nan
    r["operating_margin"] = _div(op, rev, pct=True)
    r["ebitda_margin"] = _div(ebitda, rev, pct=True) if not bank else np.nan
    r["net_margin"] = _div(ni, rev, pct=True)
    r["roe"] = _div(ni_parent, avg(eq_parent), pct=True)
    r["roa"] = _div(ni, avg(ta), pct=True)
    invested = eq + debt - cash.fillna(0) - sti
    r["roic"] = _div(ebit * (1 - tax_rate), avg(invested), pct=True) if not bank else np.nan

    r["current_ratio"] = _div(ca, cl)
    r["quick_ratio"] = _div(ca - inv.fillna(0), cl)
    r["cash_ratio"] = _div(cash + sti, cl)

    r["debt_to_equity"] = _div(debt, eq)
    r["liabilities_to_equity"] = _div(tl, eq)
    r["liabilities_to_assets"] = _div(tl, ta, pct=True)
    r["net_debt_to_ebitda"] = _div(debt - cash.fillna(0) - sti, ebitda) if not bank else np.nan
    r["interest_coverage"] = _div(ebit, interest) if not bank else np.nan
    r["equity_multiplier"] = _div(avg(ta), avg(eq))

    r["asset_turnover"] = _div(rev, avg(ta))
    r["inventory_turnover"] = _div(cogs, avg(inv))
    r["dio"] = _div(365 * avg(inv), cogs)
    r["dso"] = _div(365 * avg(recv), rev)
    r["dpo"] = _div(365 * avg(pay), cogs)
    r["ccc"] = r["dio"] + r["dso"] - r["dpo"]

    # Tăng trưởng: so với kỳ trước (năm) hoặc cùng kỳ năm trước (quý) trên số TỪNG KỲ
    shares = shares_series(wide)
    eps_period = _div(_col(wide, "net_income_parent").where(_col(wide, "net_income_parent").notna(),
                                                             _col(wide, "net_income")), shares)
    for key, s in (("revenue_growth", rev_raw), ("net_income_growth", _col(wide, "net_income")),
                   ("eps_growth", eps_period), ("equity_growth", eq), ("assets_growth", ta)):
        prev = _lag(s, period)
        r[key] = _div(s - prev, prev.abs(), pct=True)

    r["fcf"] = cfo - capex
    r["cfo_to_net_income"] = _div(cfo, ni)
    r["fcf_margin"] = _div(cfo - capex, rev, pct=True)
    r["capex_to_revenue"] = _div(capex, rev, pct=True)
    r["dividend_payout"] = _div(div_paid, ni_parent, pct=True)

    r["eps"] = _div(ni_parent, shares)
    r["bvps"] = _div(eq_parent, shares)
    r["dps"] = _div(div_paid, shares)

    if bank:
        r["loan_to_deposit"] = _div(_col(wide, "customer_loans"), _col(wide, "customer_deposits"), pct=True)
        r["equity_to_assets"] = _div(eq, ta, pct=True)
        r["provision_to_income"] = _div(flow(_col(wide, "provision_expense").abs()), rev, pct=True)

    r = r.replace([np.inf, -np.inf], np.nan)
    return r.dropna(axis=1, how="all")


def ratio_table(ratios: pd.DataFrame) -> pd.DataFrame:
    """Bảng hiển thị: dòng = chỉ số (có nhóm, nhãn), cột = kỳ (nhãn đẹp)."""
    if ratios.empty:
        return pd.DataFrame()
    rows = []
    for key in RATIO_META:
        if key not in ratios.columns:
            continue
        label, group, fmt, _ = RATIO_META[key]
        row = {"Nhóm": group, "Chỉ số": label, "_key": key, "_fmt": fmt}
        for k, v in ratios[key].items():
            row[key_to_label(k)] = v
        rows.append(row)
    return pd.DataFrame(rows)


def cagr(series: pd.Series, years: int) -> Optional[float]:
    """CAGR n năm trên số liệu NĂM (cần giá trị dương ở hai đầu)."""
    s = series.dropna()
    s = s[[int(k) % 10 == 0 for k in s.index]] if len(s) else s
    if len(s) < years + 1:
        return None
    start, end = float(s.iloc[-(years + 1)]), float(s.iloc[-1])
    if start <= 0 or end <= 0:
        return None
    return ((end / start) ** (1 / years) - 1) * 100


# ─────────────────────────────────────────────────────────────────────────────
# Valuation snapshot (cần giá hiện tại)
# ─────────────────────────────────────────────────────────────────────────────

def valuation_snapshot(wide: pd.DataFrame, price: Optional[float], period: Optional[str] = None,
                       ratios: Optional[pd.DataFrame] = None) -> Dict[str, Any]:
    """Định giá tại giá hiện tại (VND/cp) dựa trên kỳ BCTC mới nhất (TTM nếu là quý)."""
    out: Dict[str, Any] = {k: None for k in VALUATION_META}
    if wide is None or wide.empty or not price:
        return out
    period = period or detect_period(wide)
    ratios = ratios if ratios is not None else compute_ratios(wide, period)
    if ratios.empty:
        return out
    valid = ratios.dropna(subset=[c for c in ("eps", "bvps") if c in ratios.columns], how="all")
    if valid.empty:
        return out
    last = valid.iloc[-1]
    shares = shares_series(wide).loc[:valid.index[-1]].dropna()
    if shares.empty:
        return out
    sh = float(shares.iloc[-1])
    mcap = price * sh
    eps, bvps, dps = last.get("eps"), last.get("bvps"), last.get("dps")
    flow = _ttm if period == "quarter" else (lambda s: s)
    k = valid.index[-1]
    rev = flow(_col(wide, "revenue")).loc[k]
    pbt = flow(_col(wide, "profit_before_tax")).loc[k]
    ebitda = pbt + np.nan_to_num(flow(_col(wide, "interest_expense").abs()).loc[k]) + flow(_col(wide, "depreciation").abs()).loc[k]
    w_last = wide.loc[k]
    debt = np.nansum([w_last.get("short_term_debt", np.nan), w_last.get("long_term_debt", np.nan)])
    cash = np.nansum([w_last.get("cash", np.nan), w_last.get("short_term_investments", np.nan)])
    ev = mcap + debt - cash + (w_last.get("minority_interest") or 0)

    def pos(v):
        return v is not None and pd.notna(v) and v > 0

    out.update({
        "price": price, "shares": sh, "market_cap": mcap, "enterprise_value": ev,
        "pe": price / eps if pos(eps) else None,
        "pb": price / bvps if pos(bvps) else None,
        "ps": mcap / rev if pos(rev) else None,
        "ev_ebitda": ev / ebitda if pos(ebitda) else None,
        "earnings_yield": eps / price * 100 if eps is not None and pd.notna(eps) else None,
        "dividend_yield": dps / price * 100 if pos(dps) else None,
        "eps_ttm": float(eps) if eps is not None and pd.notna(eps) else None,
        "bvps": float(bvps) if bvps is not None and pd.notna(bvps) else None,
        "as_of_period": key_to_label(valid.index[-1]),
    })
    return out


# ─────────────────────────────────────────────────────────────────────────────
# DuPont, Piotroski F-score, Altman Z''-score
# ─────────────────────────────────────────────────────────────────────────────

def dupont(ratios: pd.DataFrame) -> pd.DataFrame:
    """ROE = Biên LN ròng × Vòng quay tài sản × Đòn bẩy tài chính (3 bước)."""
    need = {"net_margin", "asset_turnover", "equity_multiplier"}
    if ratios.empty or not need <= set(ratios.columns):
        return pd.DataFrame()
    d = ratios[["net_margin", "asset_turnover", "equity_multiplier"]].copy()
    d["roe_dupont"] = d["net_margin"] / 100 * d["asset_turnover"] * d["equity_multiplier"] * 100
    if "roe" in ratios.columns:
        d["roe_reported"] = ratios["roe"]
    return d.dropna(how="all")


def piotroski(wide: pd.DataFrame) -> Dict[str, Any]:
    """
    Piotroski F-score (0–9) trên 2 năm gần nhất (dữ liệu NĂM). Tiêu chí nào thiếu dữ liệu
    được bỏ qua và báo rõ số tiêu chí đã chấm.
    """
    annual = wide[[int(k) % 10 == 0 for k in wide.index]] if not wide.empty else wide
    if len(annual) < 2:
        return {"score": None, "max": 0, "checks": [], "note": "Cần ít nhất 2 năm BCTC"}
    r = compute_ratios(annual, "year")
    t, p = annual.index[-1], annual.index[-2]
    g = lambda df, c, k: (float(df.loc[k, c]) if c in df.columns and pd.notna(df.loc[k, c]) else None)  # noqa: E731
    ta_t, ta_p = g(annual, "total_assets", t), g(annual, "total_assets", p)
    ni_t, ni_p = g(annual, "net_income", t), g(annual, "net_income", p)
    roa_t = ni_t / ta_t if ni_t is not None and ta_t else None
    roa_p = ni_p / ta_p if ni_p is not None and ta_p else None
    cfo_t = g(annual, "cfo", t)
    ltd_t, ltd_p = g(annual, "long_term_debt", t), g(annual, "long_term_debt", p)
    cr_t, cr_p = g(r, "current_ratio", t), g(r, "current_ratio", p)
    sh = shares_series(annual)
    sh_t, sh_p = (float(sh.loc[t]) if pd.notna(sh.loc[t]) else None), (float(sh.loc[p]) if pd.notna(sh.loc[p]) else None)
    gm_t, gm_p = g(r, "gross_margin", t), g(r, "gross_margin", p)
    at_t = (g(annual, "revenue", t) / ta_t) if g(annual, "revenue", t) and ta_t else None
    at_p = (g(annual, "revenue", p) / ta_p) if g(annual, "revenue", p) and ta_p else None

    def chk(name, cond):
        return {"name": name, "pass": (None if cond is None else bool(cond))}

    def both(a, b):
        return a is not None and b is not None

    checks = [
        chk("ROA dương", None if roa_t is None else roa_t > 0),
        chk("Dòng tiền HĐKD dương", None if cfo_t is None else cfo_t > 0),
        chk("ROA tăng so với năm trước", (roa_t > roa_p) if both(roa_t, roa_p) else None),
        chk("CFO > LNST (chất lượng lợi nhuận)", (cfo_t > ni_t) if both(cfo_t, ni_t) else None),
        chk("Nợ vay dài hạn/Tổng TS giảm",
            (ltd_t / ta_t <= ltd_p / ta_p) if both(ltd_t, ltd_p) and ta_t and ta_p else None),
        chk("Hệ số thanh toán hiện hành tăng", (cr_t > cr_p) if both(cr_t, cr_p) else None),
        chk("Không phát hành thêm cổ phiếu", (sh_t <= sh_p * 1.001) if both(sh_t, sh_p) else None),
        chk("Biên lợi nhuận gộp tăng", (gm_t > gm_p) if both(gm_t, gm_p) else None),
        chk("Vòng quay tài sản tăng", (at_t > at_p) if both(at_t, at_p) else None),
    ]
    scored = [c for c in checks if c["pass"] is not None]
    score = sum(1 for c in scored if c["pass"])
    return {"score": score if scored else None, "max": len(scored), "checks": checks,
            "year": key_to_label(t),
            "interpretation": None if not scored else
            ("Mạnh" if score >= 7 else "Trung bình" if score >= 4 else "Yếu") + f" ({score}/{len(scored)})"}


def altman_z(wide: pd.DataFrame) -> Dict[str, Any]:
    """
    Altman Z''-score phiên bản thị trường mới nổi (Altman 2005), áp dụng cho DN phi tài chính:
      Z'' = 3.25 + 6.56·X1 + 3.26·X2 + 6.72·X3 + 1.05·X4
      X1 = (TSNH − Nợ NH)/TTS, X2 = LNST chưa phân phối/TTS, X3 = EBIT/TTS, X4 = VCSH/Nợ phải trả
      Vùng: > 5.85 an toàn · 4.35–5.85 cảnh báo · < 4.35 nguy cơ
    """
    if wide is None or wide.empty or is_bank(wide):
        return {"score": None, "note": "Không áp dụng cho ngân hàng / thiếu dữ liệu"}
    annual = wide[[int(k) % 10 == 0 for k in wide.index]]
    src = annual if not annual.empty else wide
    last = src.iloc[-1]
    ta = last.get("total_assets")
    need = ["current_assets", "current_liabilities", "retained_earnings", "profit_before_tax", "equity"]
    if not ta or any(pd.isna(last.get(c)) for c in need):
        return {"score": None, "note": "Thiếu chỉ tiêu để tính Z-score"}
    tl = last.get("total_liabilities")
    tl = tl if tl and pd.notna(tl) else ta - last["equity"]
    ebit = last["profit_before_tax"] + abs(last.get("interest_expense") or 0)
    x1 = (last["current_assets"] - last["current_liabilities"]) / ta
    x2 = last["retained_earnings"] / ta
    x3 = ebit / ta
    x4 = last["equity"] / tl if tl else np.nan
    z = 3.25 + 6.56 * x1 + 3.26 * x2 + 6.72 * x3 + 1.05 * x4
    zone = "An toàn" if z > 5.85 else "Vùng cảnh báo" if z >= 4.35 else "Nguy cơ kiệt quệ tài chính"
    return {"score": round(float(z), 2), "zone": zone, "period": key_to_label(src.index[-1]),
            "components": {"X1": x1, "X2": x2, "X3": x3, "X4": x4}}


def summarize(wide: pd.DataFrame, period: Optional[str] = None, price: Optional[float] = None) -> Dict[str, Any]:
    """Gói đầy đủ cho giao diện / báo cáo."""
    period = period or detect_period(wide)
    ratios = compute_ratios(wide, period)
    out = {
        "period": period, "ratios": ratios, "table": ratio_table(ratios),
        "valuation": valuation_snapshot(wide, price, period, ratios),
        "dupont": dupont(ratios), "is_bank": is_bank(wide),
        "piotroski": piotroski(wide) if period == "year" else None,
        "altman": altman_z(wide),
        "cagr": {},
    }
    if period == "year" and not wide.empty:
        for name, col in (("revenue", "revenue"), ("net_income", "net_income")):
            if col in wide.columns:
                out["cagr"][f"{name}_3y"] = cagr(wide[col], 3)
                out["cagr"][f"{name}_5y"] = cagr(wide[col], 5)
    return out
