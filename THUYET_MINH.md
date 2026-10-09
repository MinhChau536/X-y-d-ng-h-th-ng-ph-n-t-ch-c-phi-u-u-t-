# THUYẾT MINH HỆ THỐNG PHÂN TÍCH CƠ HỘI ĐẦU TƯ CỔ PHIẾU

## 1. Mục tiêu
Xây dựng hệ thống tự động: người dùng nhập mã cổ phiếu (hoặc chọn một rổ như VN30), hệ thống thu thập dữ liệu, phân tích, chấm điểm, đưa ra khuyến nghị và **xuất báo cáo PDF theo format báo cáo phân tích của công ty chứng khoán**.

## 2. Kiến trúc

```
                 ┌────────────────────── TẦNG DỮ LIỆU ──────────────────────┐
  Người dùng     │ fundamentals.py  BCTC năm HSX/HNX (vnfinancialdata/arminer)│
  (web / CLI)    │ analyzer.py      Giá & VN-Index (vnstock – Vietcap)        │
      │          │ news.py          Tin tức (vnstock / Google News RSS)       │
      ▼          │ data/companies_icb.csv  Danh mục DN & ngành ICB (arminer)  │
  app.py ───────►└───────────────────────────┬───────────────────────────────┘
  main.py                                    ▼
  screener.py    ┌──────────────────── TẦNG PHÂN TÍCH ──────────────────────┐
                 │ Chỉ báo kỹ thuật · So sánh ngành · Cảm xúc tin tức        │
                 │ Chấm điểm 4 trụ cột · Giá mục tiêu · Cắt lỗ · Đối chiếu   │
                 └───────────────────────────┬───────────────────────────────┘
                                             ▼
                 ┌──────────────────── TẦNG BÁO CÁO ────────────────────────┐
                 │ report.py   PDF từng mã (4 trang)                         │
                 │ screener.py PDF sàng lọc thị trường + CSV xếp hạng        │
                 └───────────────────────────────────────────────────────────┘
```

| File | Chức năng |
|---|---|
| `fundamentals.py` | Đọc BCTC, ánh xạ chỉ tiêu đa ngành (DN thường, ngân hàng, CTCK, bảo hiểm), tính ROE, ROA, biên LN, nợ/VCSH, EPS, BVPS, kiểm tra chất lượng dữ liệu |
| `news.py` | Tin doanh nghiệp + tin thị trường chung theo chủ đề, chấm cảm xúc theo từ điển từ khoá tiếng Việt |
| `analyzer.py` | Lấy giá, chỉ báo kỹ thuật, so sánh ngành, đối chiếu chéo dữ liệu, chấm điểm, khuyến nghị |
| `report.py` | Vẽ biểu đồ, dựng PDF |
| `screener.py` | Quét cả rổ cổ phiếu, xếp hạng, PDF tổng hợp |
| `snapshot.py` | Đọc ảnh chụp dữ liệu thật (giá nén delta, tin tức) khi không gọi được API |
| `app.py` / `main.py` | Giao diện web Streamlit / dòng lệnh |

## 3. Nguồn dữ liệu (theo yêu cầu đề bài)

| Yêu cầu | Nguồn trong hệ thống |
|---|---|
| Giá và dữ liệu giao dịch | API chart DNSE (giá ngày đã điều chỉnh, cách lấy kế thừa từ `DNSE.py` của repo TELEGRAM-BOT-CHỨNG-KHOÁN); dự phòng vnstock; dự phòng cuối là ảnh chụp dữ liệu thật VN30 + VN-Index phiên 08/10/2026 (`data/prices_raw`, đã đối chiếu checksum với API) |
| BCTC và chỉ số tài chính | Bộ BCTC năm 2009–2025 của DN niêm yết HSX/HNX (vnfinancialdata – TS. Ngô Phú Thanh, UEL), kế thừa qua repo tham khảo **vn-annual-report-miner**; chỉ số vnstock dùng để đối chiếu |
| Tin tức doanh nghiệp | vnstock company.news(); Google News RSS tiếng Việt; dự phòng ảnh chụp 132 tin thật ngày 09/10/2026 (`data/news_raw`) |
| Tin tức thị trường chung | Google News RSS 7 ngày theo 4 chủ đề: VN-Index, khối ngoại, vĩ mô (lãi suất, tỷ giá), nâng hạng |
| Format báo cáo CTCK | Hộp khuyến nghị, giá mục tiêu, dư địa, luận điểm đầu tư, thẻ điểm, biểu đồ, bảng chỉ số, phương pháp, miễn trừ trách nhiệm |
| Nguồn khác | Danh mục DN & phân ngành ICB 4 cấp (FiinPro/Vietcap IQ) từ repo tham khảo |

**Kế thừa từ repo tham khảo vn-annual-report-miner:** bộ dữ liệu BCTC dạng parquet, bảng ánh xạ tên chỉ tiêu đa ngành (`ITEM_MAPPING` của `FinancialDataProvider`), danh mục ngành ICB, và cách tiếp cận chấm điểm văn bản bằng từ điển từ khoá (áp dụng cho tin tức).

## 4. Phương pháp phân tích

**Điểm tổng hợp = 35% Chất lượng + 30% Định giá + 25% Động lượng + 10% Tin tức**

| Trụ cột | Tiêu chí |
|---|---|
| Chất lượng DN | ROE ≥ 15%; ROA ≥ 5% (TCTD ≥ 1%); biên LN ròng ≥ 10%; nợ/VCSH < 1 (miễn với TCTD); tăng trưởng DT, LNST ≥ 10%; ROE và biên LN cao hơn trung vị ngành ICB cấp 3 |
| Định giá | P/E dương; P/E, P/B thấp hơn trung vị lịch sử của chính DN; P/E < 15x |
| Động lượng | Giá > MA50; MA50 > MA200; RSI 40–70; lợi suất 6 tháng vượt VN-Index; VN-Index trên MA200 |
| Tin tức | (Cảm xúc tổng hợp + 1) × 50; cảm xúc tổng hợp = 70% tin doanh nghiệp (90 ngày) + 30% tâm lý thị trường chung (7 ngày) |

- **Khuyến nghị:** MUA khi ≥ 70 điểm và giá mục tiêu > giá hiện tại; THEO DÕI/NẮM GIỮ khi 50–70; TRÁNH/BÁN khi < 50.
- **Giá mục tiêu** = bình quân (EPS × P/E trung vị lịch sử; BVPS × P/B trung vị lịch sử). P/E, P/B lịch sử = giá đóng cửa (đã điều chỉnh) cuối năm / EPS, BVPS năm đó quy về số cổ phiếu hiện tại (cùng cơ sở với giá điều chỉnh). Loại P/E âm hoặc > 60x (năm lãi gần 0), P/B > 15x; dư địa giới hạn ±50%.
- **Cắt lỗ gợi ý** = giá hiện tại − 2 × ATR(14).

## 5. Kiểm soát độ chính xác dữ liệu
1. **Đối chiếu chéo 2 nguồn:** doanh thu, LNST, EPS, ROE từ bộ BCTC được so với vnstock cho 2 năm gần nhất; chênh lệch > 5% được tô đỏ trong PDF.
2. **Phát hiện năm bị sao chép:** năm có doanh thu và LNST trùng y hệt năm trước bị loại (ví dụ phát hiện thực tế: SSI năm 2025).
3. **Phát hiện EPS bất thường:** EPS > 1 triệu đồng (khớp nhầm dòng) được tính lại = LNST / số cổ phiếu.
4. **Lấy dòng tổng:** với tổng tài sản, VCSH, nợ phải trả, chọn giá trị lớn nhất trong các dòng cùng tên để tránh lấy nhầm chỉ tiêu con.
5. **Minh bạch nguồn:** mọi PDF ghi rõ nguồn giá, nguồn BCTC, phiên giá cuối, thời điểm tạo báo cáo.

## 6. Hướng dẫn vận hành
```
pip install -r requirements.txt
streamlit run app.py                    # giao diện web
python main.py FPT HPG VCB              # PDF từng mã
python screener.py --group VN30 --top 5 # quét rổ, xếp hạng
python main.py FPT --demo               # kiểm thử không cần mạng (giá & tin mô phỏng)
```

## 7. Hạn chế và hướng phát triển
- BCTC theo năm, chưa có số quý gần nhất; bổ sung BCTC quý để cập nhật nhanh hơn.
- Chấm cảm xúc dựa trên từ khoá, chưa hiểu ngữ cảnh; nâng cấp bằng mô hình NLP tiếng Việt (PhoBERT).
- Giá mục tiêu dựa trên bội số lịch sử; bổ sung định giá DCF và so sánh P/E ngành.
- Quét toàn sàn bị giới hạn tốc độ API miễn phí; thêm bộ nhớ đệm giá vào SQLite.
- Tích hợp khai phá báo cáo thường niên (quét từ khoá ESG, chuyển đổi số) bằng module `arminer scan` của repo tham khảo.
- Ý tưởng sức mạnh tương đối 6 tháng, xu hướng thị trường (VN-Index/MA200) và cắt lỗ ATR tham khảo từ pipeline 3 tầng của repo TELEGRAM-BOT-CHỨNG-KHOÁN.
- Gửi báo cáo tự động hàng ngày qua Telegram bot (ý tưởng từ repo TELEGRAM-BOT-CHỨNG-KHOÁN).

*Báo cáo do hệ thống tạo tự động phục vụ học tập, không phải khuyến nghị đầu tư.*
