"""
Trang – Báo cáo thường niên & BCTC dạng PDF theo năm: dò tìm, tải về, tải lên, trích số liệu.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st

from components.ui import fmt_num, page_header, symbol_input
from data.financial_mapping import ITEMS_BY_KEY
from services.document_service import DOC_TYPES, DocumentService, period_key_for
from services.stock_service import StockService


def render():
    page_header("📚 Báo Cáo Thường Niên & BCTC (PDF)",
                "Dò tìm tài liệu trên Vietstock, CafeF và trang Quan hệ cổ đông của doanh nghiệp · tải về theo năm · "
                "trích số liệu BCTC từ PDF theo mã số VAS")
    symbol = symbol_input("doc_symbol")
    if not symbol:
        return
    ds = DocumentService()

    c1, c2 = st.columns([1, 3])
    with c1:
        if st.button("🔎 Dò tìm tài liệu", type="primary", use_container_width=True):
            with st.spinner("Đang dò tìm trên các nguồn..."):
                info = StockService(symbol).get_company_info()
                found = ds.discover(symbol, info)
            st.success(f"Tìm thấy {len(found)} tài liệu (BCTN/BCTC) cho {symbol}.")
    with c2:
        st.caption("Các nguồn tài liệu là trang web công khai, có thể thay đổi cấu trúc. Nếu không tìm thấy, "
                   "hãy dán link PDF hoặc tải file lên ở bên dưới – hệ thống vẫn phân loại & trích số liệu.")

    docs = ds.list_documents(symbol)
    tab_list, tab_add, tab_extract = st.tabs(["📂 Danh sách tài liệu", "➕ Thêm tài liệu", "🧾 Trích số liệu từ PDF"])

    with tab_list:
        if docs.empty:
            st.info("Chưa có tài liệu. Bấm “Dò tìm tài liệu” hoặc thêm tài liệu ở tab bên cạnh.")
        else:
            types = st.multiselect("Loại tài liệu", list(DOC_TYPES), default=["annual_report", "fs_annual"],
                                   format_func=DOC_TYPES.get)
            years = sorted({int(y) for y in docs["year"].dropna()}, reverse=True)
            view = docs[docs["doc_type"].isin(types)] if types else docs
            for y in years + [None]:
                sub = view[view["year"] == y] if y is not None else view[view["year"].isna()]
                if sub.empty:
                    continue
                st.markdown(f"**{y if y else 'Không rõ năm'}**")
                for _, d in sub.iterrows():
                    a, b, c = st.columns([5, 2, 2])
                    a.markdown(f"{d['doc_type_label']} · {d['title'] or ''}  \n"
                               f"<span style='font-size:11px;color:#64748b'>nguồn: {d['source']}</span>",
                               unsafe_allow_html=True)
                    if d["url"]:
                        b.link_button("🌐 Mở link gốc", d["url"], use_container_width=True)
                    if d["downloaded"]:
                        path = Path(d["local_path"])
                        c.download_button("⬇️ Tải file", path.read_bytes(), file_name=path.name,
                                          key=f"dl_{d['doc_id']}", use_container_width=True)
                    elif d["url"] and c.button("💾 Lưu về máy chủ", key=f"save_{d['doc_id']}", use_container_width=True):
                        with st.spinner("Đang tải..."):
                            p = ds.download(d.to_dict())
                        st.success("Đã lưu.") if p else st.error("Không tải được file từ nguồn.")
                        st.rerun()

    with tab_add:
        st.markdown("**Tải file lên** (PDF BCTC / BCTN)")
        up = st.file_uploader("Chọn file", type=["pdf"], key="doc_upload")
        c1, c2, c3 = st.columns(3)
        with c1:
            dtype = st.selectbox("Loại", list(DOC_TYPES)[:4], format_func=DOC_TYPES.get, key="up_type")
        with c2:
            year = st.number_input("Năm", 2005, 2100, value=pd.Timestamp.now().year - 1, key="up_year")
        with c3:
            quarter = st.selectbox("Quý (nếu là BCTC quý)", [None, 1, 2, 3, 4], key="up_q")
        if up is not None and st.button("Lưu tài liệu", key="up_save"):
            ds.save_upload(symbol, up.name, up.getvalue(), dtype, int(year), quarter)
            st.success(f"Đã lưu {up.name}.")
            st.rerun()
        st.markdown("---")
        st.markdown("**Hoặc dán link PDF**")
        url = st.text_input("Link tài liệu", key="doc_url")
        title = st.text_input("Tiêu đề (để phân loại năm/loại tự động)", key="doc_title")
        if url and st.button("Thêm link", key="doc_add_link"):
            doc = ds.add_link(symbol, url, title)
            st.success(f"Đã thêm: {DOC_TYPES.get(doc['doc_type'])} {doc.get('year') or ''}")
            st.rerun()

    with tab_extract:
        fs_docs = docs[docs["doc_type"].str.startswith("fs_") & docs["downloaded"]] if not docs.empty else docs
        if fs_docs.empty:
            st.info("Cần ít nhất một file BCTC (PDF) đã lưu về máy chủ.")
            return
        pick = st.selectbox("Chọn BCTC", fs_docs["doc_id"].tolist(),
                            format_func=lambda i: f"{fs_docs.set_index('doc_id').loc[i, 'doc_type_label']} "
                                                  f"{fs_docs.set_index('doc_id').loc[i, 'year']} – "
                                                  f"{fs_docs.set_index('doc_id').loc[i, 'title']}")
        if st.button("Trích số liệu", type="primary"):
            doc = fs_docs.set_index("doc_id").loc[pick].to_dict()
            doc["doc_id"] = pick
            with st.spinner("Đang đọc PDF..."):
                res = ds.extract(doc)
            if not res.get("values"):
                st.warning(res.get("note") or "Không trích được số liệu (PDF có thể là bản scan hoặc khác mẫu VAS).")
                return
            chk = res.get("checks", {})
            st.success(f"Trích được {len(res['values'])} chỉ tiêu · đơn vị gốc ×{fmt_num(res['unit'], 0)} · "
                       f"kiểm tra cân đối: {'✅ khớp' if chk.get('balance_identity') else '⚠️ chưa khớp / thiếu'}")
            rows = [{"Chỉ tiêu": ITEMS_BY_KEY[k].label_vi if k in ITEMS_BY_KEY else k,
                     "Giá trị (tỷ đồng)": fmt_num(v / 1e9, 1) if k != "eps" else fmt_num(v, 0) + " đ/cp"}
                    for k, v in res["values"].items()]
            # Đối chiếu với số liệu từ nguồn trực tuyến
            pk = period_key_for(doc)
            online = StockService(symbol).get_financials("year" if doc["doc_type"] == "fs_annual" else "quarter")
            data = online.get("data", pd.DataFrame())
            if pk and data is not None and not data.empty and pk in data.index:
                for row, (k, v) in zip(rows, res["values"].items()):
                    ov = data.loc[pk].get(k)
                    if ov is not None and pd.notna(ov) and k != "eps":
                        row["Nguồn trực tuyến (tỷ)"] = fmt_num(ov / 1e9, 1)
                        row["Chênh lệch %"] = fmt_num((v - ov) / abs(ov) * 100, 2, "%") if ov else "–"
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
            st.caption("Số liệu trích từ PDF được dùng làm nguồn dự phòng cuối cùng trong chuỗi BCTC "
                       "(chỉ bù các kỳ/chỉ tiêu mà vnstock và Vietstock không có).")
