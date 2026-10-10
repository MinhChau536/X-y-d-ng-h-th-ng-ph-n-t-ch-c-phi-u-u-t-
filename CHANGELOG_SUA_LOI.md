# Nhật ký sửa lỗi – 10/10/2026

| # | Vấn đề | Cách sửa | File |
|---|---|---|---|
| 1 | PDF tự sinh số liệu giả khi thiếu dữ liệu (giá hình sin, điểm mặc định 65/70/60, bảng BCTC 5 năm nội suy 85%/năm, trung vị ngành gõ tay, 3 tin tức viết sẵn, tiêu chí "Biến động an toàn" luôn 20/20, giá mục tiêu mặc định +15%) | Viết lại `_prepare_data`: chỉ dùng số liệu thật, thiếu thì `None` → "N/A"; không có điểm tổng thì khuyến nghị "CHƯA ĐỦ DỮ LIỆU". Bảng giải trình trang 3 lấy đúng các thành phần đã chấm. Bảng KQKD lấy từ chuỗi BCTC thật theo kỳ. Tin tức lấy từ CompanyNewsService. | `reports/pdf_generator.py`, `pages/pdf_report.py` |
| 2 | Điểm rủi ro: mẫu số luôn 100 dù chỉ có Volatility + MDD → tối đa 60 | Chỉ cộng mẫu số cho thành phần có dữ liệu; thêm Beta (so với VN-Index) và Nợ/VCSH thật. Sửa cùng lỗi ở điểm sức khỏe thị trường. | `analytics/opportunity_score.py`, `services/stock_service.py` |
| 3 | Chiến lược Custom chỉ sinh 1/0 → mua rồi giữ đến hết kỳ | Thêm điều kiện thoát: giá < SMA50, SMA20 < SMA50 (nếu bật), hoặc RSI > ngưỡng chốt lời (mặc định 80, chỉnh trên giao diện) | `analytics/backtesting.py`, `pages/backtest.py` |
| 4 | "Tăng trưởng doanh thu" thực chất là QoQ; không kiểm tra thứ tự kỳ | Nhận diện kỳ (Năm/Kỳ hoặc nhãn "Q3/2025"), sắp xếp tăng dần, so với cùng quý năm trước; ghi rõ cơ sở so sánh | `analytics/period_utils.py` (mới), `analytics/fundamental.py`, `analytics/valuation.py` |
| 5 | Định giá "so sánh ngành" dùng hằng số P/E 15, P/B 1.5 | Tính trung vị P/E, P/B, ROE, biên LN, Nợ/VCSH từ tối đa 8 DN cùng nhóm ngành (cần ≥ 3 DN, lọc ngoại lai). Điểm định giá chấm theo tỷ lệ so với ngành. Không đủ dữ liệu ngành thì dùng mặc định và ghi rõ. | `analytics/peers.py` (mới), `analytics/valuation.py`, `services/stock_service.py` |
| 6 | RSI có 2 công thức khác nhau | Một hàm `rsi_wilder` dùng chung cho kỹ thuật, động lượng, backtest | `analytics/indicators.py` (mới) |
| 7 | ADX, MFI, OBV, CMF tính nhưng không vào điểm | Điểm kỹ thuật mới: MA 25, RSI 15, MACD 15, KL 10, Bollinger 10, ADX+DI 10, Dòng tiền CMF/MFI/OBV 15; thành phần thiếu được loại khỏi mẫu số | `analytics/technical.py` |

Kiểm thử: `pytest tests/ -v` → 29/29 passed (13 test mới trong `tests/test_fixes.py`).

---

# Phiên bản 2.0 – Nền tảng dữ liệu đa nguồn (10/10/2026)

## Dữ liệu
- **Giá lai ghép**: 365 ngày gần nhất từ DNSE (API biểu đồ công khai), phần cũ hơn từ vnstock VCI → KBS → MSN → Vietstock. Quy về VND, tự điều chỉnh hệ số ở điểm nối khi hai nguồn lệch (cổ tức / chia tách), ghi nguồn từng dòng (`data/data_repository.py`).
- **BCTC nhiều năm, nhiều nguồn**: VCI → KBS → Vietstock → PDF BCTC đã tải; nguồn sau bù ô còn thiếu; lưu nguồn từng ô; lưu DuckDB để dùng khi mất mạng.
- **Bộ chuẩn hóa BCTC** (`data/financial_mapping.py`): ~45 chỉ tiêu chuẩn, khớp theo item_id / nhãn Việt (có-không dấu) / nhãn Anh với danh sách loại trừ; xử lý kỳ mới-nhất-trước, cột trùng, đơn vị "tỷ/triệu đồng"; bảng chỉ số theo quý được quy về năm; số dư cuối năm được gán cho Q4.
- **vnstock 4.x** (kiểm tra theo mã nguồn 4.0.9), tương thích ngược 3.x; Vietstock client mới (thử nghiệm).
- **DuckDB an toàn đa luồng** (mỗi luồng một cursor) – trước đây chạy song song có thể treo.

## Phân tích
- **Bộ tính chỉ số từ BCTC** (`analytics/financial_ratios.py`): ~40 chỉ số, TTM cho kỳ quý, bình quân đầu–cuối kỳ, định giá tại giá hiện tại (P/E, P/B, P/S, EV/EBITDA, tỷ suất cổ tức), DuPont, Piotroski F-score, Altman Z''-score, CAGR, bộ chỉ số ngân hàng.
- Phân tích cơ bản và định giá dùng chỉ số tính từ BCTC (EPS/BVPS TTM) thay cho bảng dựng sẵn.

## Tài liệu & tin tức
- **Kho BCTN / BCTC PDF theo năm** (`services/document_service.py`): dò tìm trên Vietstock, CafeF, website Quan hệ cổ đông; tự phân loại (BCTN, BCTC năm/bán niên/quý, hợp nhất/riêng) và gắn năm; tải về, tải lên, dán link.
- **Trích BCTC từ PDF theo mã số VAS** (`data/pdf_financial_extractor.py`) có kiểm tra cân đối; dùng làm nguồn dự phòng cuối.
- **Tin tức lưu theo ngày** vào DuckDB; bảng tin cho danh mục theo dõi; bỏ việc gán ngày giả cho tin cào từ CafeF.

## Tính năng mới
- 7 trang mới: Báo cáo tài chính, Chỉ số tài chính, Tài liệu BCTN & BCTC, Bộ lọc cổ phiếu, So sánh cổ phiếu, Theo dõi & cảnh báo, Nguồn dữ liệu.
- **Xuất Excel** BCTC + chỉ số + nguồn từng ô + bảng gốc (`reports/excel_export.py`).
- **PDF chọn mục theo nhu cầu**, thêm mục BCTC nhiều năm và Chỉ số tài chính (ô chọn chương trên trang PDF trước đây không có tác dụng).
- **Script cập nhật hằng ngày** (`scripts/daily_update.py`) + hướng dẫn lên lịch Windows / macOS / Linux.

## Kiểm thử
- 50 test (thêm `tests/test_v2_platform.py`, dữ liệu giả lập đúng định dạng vnstock 4.x trong `tests/fakes.py`, PDF BCTC mẫu trong `tests/pdf_samples.py`); test chạy trên CSDL bộ nhớ, không đụng dữ liệu thật.
- Đã chạy thử toàn bộ 15 trang bằng Streamlit AppTest và chụp màn hình giao diện với dữ liệu giả lập.
