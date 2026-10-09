# Hệ thống phân tích cơ hội đầu tư cổ phiếu

Cài đặt (1 lần):   pip install -r requirements.txt

Giao diện web:     streamlit run app.py
Từng mã:           python main.py FPT HPG VCB
Quét thị trường:   python screener.py --group VN30 --top 5
Kiểm thử offline:  python main.py FPT --demo   (BCTC thật, giá & tin mô phỏng)

PDF xuất ra thư mục output/. Thuyết minh chi tiết: THUYET_MINH.md

Nguồn dữ liệu BCTC & ngành ICB kế thừa từ repo vn-annual-report-miner (MIT License,
© Trương Minh Quân), dựa trên bộ dữ liệu vnfinancialdata của TS. Ngô Phú Thanh (UEL).
