# 📈 STOCK ANALYTICS PRO v2
### Nền tảng phân tích chứng khoán Việt Nam – dữ liệu đa nguồn, BCTC nhiều năm, báo cáo tự động

> Đồ án học thuật ứng dụng thực tế. Giá gần nhất từ **DNSE**, giá lịch sử từ **vnstock / Vietstock**,
> BCTC kết hợp **nhiều nguồn có dự phòng**, **tự tính chỉ số tài chính từ BCTC**, kho **báo cáo thường niên
> & BCTC PDF theo năm**, tin tức lưu theo ngày, bộ lọc – so sánh – cảnh báo, và **báo cáo PDF chọn mục theo nhu cầu**.

---

## 🧭 15 trang chức năng

| Nhóm | Trang | Nội dung |
|---|---|---|
| Thị trường | 🏛️ Tổng quan thị trường | VN-Index, VN30, HNX, UPCoM; so sánh hiệu suất; sức khỏe thị trường |
| Doanh nghiệp | 🔍 Phân tích cổ phiếu | Hồ sơ, giá, kỹ thuật, cơ bản, định giá, tin tức của một mã |
| | 📑 Báo cáo tài chính | KQKD / CĐKT / LCTT **nhiều năm hoặc theo quý**, nguồn của từng ô, bảng gốc từng nguồn, **tải Excel** |
| | 🧮 Chỉ số tài chính | ~40 chỉ số tính từ BCTC, định giá tại giá hiện tại, DuPont, Piotroski F-score, Altman Z''-score, CAGR |
| | 📚 Tài liệu BCTN & BCTC | Dò tìm, tải về **báo cáo thường niên & BCTC PDF theo năm**, tải lên tay, **trích số liệu từ PDF** |
| | 📈 Phân tích kỹ thuật | SMA/EMA, RSI, MACD, Bollinger, ATR, ADX±DI, MFI, OBV, CMF, hỗ trợ/kháng cự |
| | 📰 Tin tức doanh nghiệp | Tin đa nguồn, phân loại sắc thái, lưu vào CSDL để xem lại theo ngày |
| Ra quyết định | ⭐ Điểm cơ hội đầu tư | Chấm điểm 0–100 từ 5 trụ cột (kỹ thuật, động lượng, cơ bản, định giá, rủi ro) |
| | 🔎 Bộ lọc cổ phiếu | Lọc theo chỉ số + 5 bộ lọc mẫu (Value, Growth, Quality, Cổ tức, Momentum), xếp hạng tổng hợp |
| | ⚖️ So sánh cổ phiếu | 2–5 mã cạnh nhau: chỉ số, định giá, giá chuẩn hóa |
| | 👁️ Theo dõi & cảnh báo | Danh mục theo dõi, cảnh báo giá / % thay đổi / RSI, bảng tin hằng ngày |
| | 🔬 Backtest | MA Crossover, RSI, Custom Rules (có điều kiện thoát), không look-ahead |
| | 💼 Danh mục đầu tư | Vị thế, lãi/lỗ theo giá gần nhất, phân bổ |
| Báo cáo | 📄 Xuất báo cáo PDF | Chọn mục: Tổng quan, Kỹ thuật, **BCTC nhiều năm**, **Chỉ số tài chính**, So sánh ngành, Giải trình điểm |
| Hệ thống | 🛰️ Nguồn dữ liệu | Trạng thái từng nguồn, nguồn gốc dữ liệu của mỗi mã, nhật ký cập nhật tự động |

---

## 🛰️ Chiến lược dữ liệu đa nguồn

```
GIÁ   ┌──────────── phần cũ hơn N ngày ───────────┐┌──── N ngày gần nhất (mặc định 365) ────┐
      vnstock VCI → KBS → MSN → Vietstock               DNSE (lỗi thì dùng nguồn lịch sử)
      • Mọi giá cổ phiếu quy về VND  • Ở điểm nối, nếu hai nguồn lệch giá (do một bên đã điều chỉnh
        cổ tức/chia tách) thì nhân đoạn cũ với hệ số để chuỗi liền mạch  • Mỗi dòng ghi rõ nguồn

BCTC  vnstock VCI ──► vnstock KBS ──► Vietstock ──► PDF BCTC đã tải (trích theo mã số VAS)
      • Mỗi nguồn được CHUẨN HÓA về cùng một bộ ~45 chỉ tiêu (data/financial_mapping.py)
      • Nguồn trước được ưu tiên; ô nào (kỳ × chỉ tiêu) còn thiếu thì lấy nguồn sau
      • Lưu nguồn của từng ô; lưu vào DuckDB để dùng khi mất kết nối

PDF   Vietstock → CafeF → website Quan hệ cổ đông của doanh nghiệp → tải lên / dán link thủ công
```

Đổi thứ tự / số ngày trong `.env`: `DNSE_RECENT_DAYS`, `PRICE_HISTORY_SOURCES`, `FINANCIAL_SOURCES`, `DOCUMENT_SOURCES`.

### Bộ chuẩn hóa BCTC – vì sao cần
Mỗi nguồn đặt tên và sắp xếp khác nhau: VCI trả ma trận chỉ tiêu × kỳ với **kỳ mới nhất đứng trước** và
có cột trùng (`2025-Q4_1`); KBS có `item_id` chuẩn nhưng chỉ 4 kỳ; bảng cũ của vnstock 3 ghi "(Tỷ đồng)".
Bộ chuẩn hóa khớp từng chỉ tiêu theo `item_id` → nhãn tiếng Việt (có/không dấu) → nhãn tiếng Anh, **loại trừ**
các dòng dễ nhầm (vd "Tăng trưởng doanh thu (%)" khi tìm "Doanh thu"), sắp kỳ đúng thời gian và quy về VND.

### Chỉ số tính từ BCTC (analytics/financial_ratios.py)
* **Sinh lời**: biên gộp, biên HĐKD, biên EBITDA, biên ròng, ROE (LNST cổ đông mẹ / VCSH mẹ bình quân), ROA, ROIC
* **Thanh khoản**: hiện hành, nhanh, tiền mặt · **Cơ cấu vốn**: nợ vay/VCSH, nợ phải trả/VCSH, nợ vay ròng/EBITDA, khả năng trả lãi
* **Hiệu quả**: vòng quay tài sản, tồn kho, DIO, DSO, DPO, chu kỳ tiền mặt
* **Tăng trưởng YoY** (năm so năm trước; quý so cùng quý năm trước), CAGR 3/5 năm
* **Dòng tiền**: FCF, CFO/LNST, biên FCF, capex/doanh thu, tỷ lệ chi trả cổ tức
* **Định giá tại giá hiện tại**: P/E (EPS TTM), P/B, P/S, EV/EBITDA, tỷ suất cổ tức, vốn hóa, EV
* **Sức khỏe**: DuPont 3 bước, Piotroski F-score (9 tiêu chí), Altman Z''-score (bản thị trường mới nổi)
* Kỳ quý dùng **TTM** (4 quý liên tiếp); tỷ số dòng/số dư dùng **bình quân đầu–cuối kỳ**; ngân hàng có bộ chỉ số riêng (LDR, VCSH/TTS…)

### Trích BCTC từ PDF (data/pdf_financial_extractor.py)
Đọc lớp chữ của PDF → tách 3 báo cáo theo tiêu đề → tìm dòng có **mã số chuẩn VAS** (TT200/202) **và** nhãn khớp
(vd mã 10 phải có "doanh thu thuần") → lấy số kỳ này → quy đổi theo "Đơn vị tính" → kiểm tra
Tổng tài sản = Nợ phải trả + VCSH. PDF bản scan (không có lớp chữ) cần OCR trước.

---

## 🏛️ Kiến trúc

```
GPM1/
├── app.py                         # điều hướng 15 trang
├── config/settings.py             # .env, chiến lược nguồn dữ liệu
├── data/
│   ├── providers/
│   │   ├── dnse_client.py         # DNSE: giá gần nhất & OHLCV (API biểu đồ công khai)
│   │   ├── vnstock_client.py      # vnstock 4.x (VCI/KBS/MSN), tương thích 3.x
│   │   └── vietstock_client.py    # Vietstock: giá & BCTC dự phòng (thử nghiệm)
│   ├── data_repository.py         # GHÉP GIÁ + CHUỖI DỰ PHÒNG BCTC + cache + DuckDB
│   ├── financial_mapping.py       # bộ chuẩn hóa BCTC đa nguồn
│   ├── pdf_financial_extractor.py # trích BCTC từ PDF theo mã số VAS
│   └── database.py                # DuckDB (an toàn đa luồng: mỗi luồng một cursor)
├── analytics/
│   ├── financial_ratios.py        # ~40 chỉ số, TTM, DuPont, F-score, Z-score, định giá
│   ├── technical.py · momentum.py · fundamental.py · valuation.py · peers.py
│   ├── opportunity_score.py · backtesting.py · indicators.py · period_utils.py
├── services/
│   ├── stock_service.py           # điều phối toàn bộ phân tích 1 mã
│   ├── document_service.py        # kho BCTN/BCTC PDF: dò tìm, tải, phân loại, trích số liệu
│   ├── company_news_service.py    # tin đa nguồn + lưu theo ngày
│   ├── watchlist_service.py       # theo dõi & cảnh báo
│   ├── screener_service.py        # bộ lọc, xếp hạng, so sánh
│   └── market_service.py · portfolio_service.py
├── reports/
│   ├── pdf_generator.py           # PDF chọn mục theo nhu cầu
│   └── excel_export.py            # BCTC + chỉ số + nguồn → Excel
├── scripts/daily_update.py        # cập nhật tự động hằng ngày
├── pages/                         # 15 trang Streamlit
└── tests/                         # 50 test (dữ liệu giả lập đúng định dạng vnstock 4.x)
```

---

## 🚀 Cài đặt & chạy

```bash
python -m venv .venv
.venv\Scripts\Activate.ps1            # Windows PowerShell   (macOS/Linux: source .venv/bin/activate)
pip install -r requirements.txt
pip install -U vnstock --extra-index-url https://vnstocks.com/api/simple   # vnstock 4.x
copy .env.example .env                # rồi chỉnh nếu cần (VNSTOCK_API_KEY không bắt buộc)
streamlit run app.py                  # mở http://localhost:8501
```

### Cập nhật tự động hằng ngày
```bash
python scripts/daily_update.py                       # giá + tin tức + cảnh báo cho mã đang theo dõi
python scripts/daily_update.py --financials --documents
```
Lên lịch trên Windows (16:30 mỗi ngày):
```
schtasks /Create /SC DAILY /ST 16:30 /TN "StockAnalyticsDaily" /TR "\"C:\...\GPM1\.venv\Scripts\python.exe\" \"C:\...\GPM1\scripts\daily_update.py\""
```
macOS/Linux: `30 16 * * 1-5 cd /duong_dan/GPM1 && .venv/bin/python scripts/daily_update.py`

### Kiểm thử
```bash
pytest tests/ -v        # 50 passed – chạy trên CSDL bộ nhớ & thư mục tạm, không đụng dữ liệu thật
```

---

## ⚠️ Giới hạn cần biết

* **Vietstock, CafeF, website doanh nghiệp** không có API chính thức – hệ thống đọc trang web công khai nên có thể
  ngừng hoạt động khi các trang đổi cấu trúc. Khi đó chuỗi dự phòng tự chuyển nguồn; tài liệu PDF luôn có thể
  tải lên hoặc dán link thủ công.
* **vnstock** bản miễn phí giới hạn số lượt gọi mỗi phút → bộ lọc nên dùng theo nhóm ngành/rổ (10–30 mã);
  kết quả được lưu cache trong ngày.
* **KBS** chỉ trả 4 kỳ BCTC gần nhất; dữ liệu nhiều năm chủ yếu đến từ VCI.
* **Giấy phép vnstock** (từ bản 4.0.8): sử dụng cá nhân/học thuật thoải mái; phân phối lại dữ liệu cho bên thứ ba
  hoặc sản phẩm có giá trị chính là cung cấp dữ liệu thị trường cần thỏa thuận riêng với tác giả.

## ⚖️ Miễn trừ trách nhiệm
Hệ thống phục vụ **nghiên cứu khoa học và học thuật**. Kết quả phân tích, chấm điểm và backtest chỉ mang tính
tham khảo, **không phải khuyến nghị đầu tư**.
