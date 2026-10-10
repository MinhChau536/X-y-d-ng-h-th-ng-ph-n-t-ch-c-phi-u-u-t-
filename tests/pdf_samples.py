"""Tạo PDF BCTC mẫu (có lớp chữ) theo mẫu biểu VAS để kiểm thử trình trích số liệu."""
from pathlib import Path

import matplotlib
from fpdf import FPDF

FONT = Path(matplotlib.get_data_path()) / "fonts" / "ttf" / "DejaVuSans.ttf"


def make_vas_pdf(unit_text: str = "Đơn vị tính: Triệu đồng") -> bytes:
    pdf = FPDF()
    pdf.add_font("DV", "", str(FONT))
    pdf.set_font("DV", size=8)

    def page(lines):
        pdf.add_page()
        for ln in lines:
            pdf.cell(0, 5, ln, new_x="LMARGIN", new_y="NEXT")

    page(["CÔNG TY CỔ PHẦN MẪU", "BÁO CÁO TÀI CHÍNH HỢP NHẤT NĂM 2025 ĐÃ ĐƯỢC KIỂM TOÁN",
          "MỤC LỤC", "Bảng cân đối kế toán hợp nhất 5", "Báo cáo kết quả hoạt động kinh doanh hợp nhất 7"])
    page(["BẢNG CÂN ĐỐI KẾ TOÁN HỢP NHẤT", "Tại ngày 31 tháng 12 năm 2025", unit_text,
          "TÀI SẢN Mã số Thuyết minh 31/12/2025 01/01/2025",
          "A. TÀI SẢN NGẮN HẠN 100 38.250 31.400",
          "I. Tiền và các khoản tương đương tiền 110 V.1 7.120 6.010",
          "II. Đầu tư tài chính ngắn hạn 120 V.2 8.000 6.500",
          "III. Các khoản phải thu ngắn hạn 130 12.400 10.900",
          "IV. Hàng tồn kho 140 V.4 6.900 5.800",
          "II. Tài sản cố định 220 15.300 13.100",
          "TỔNG CỘNG TÀI SẢN 270 70.500 61.200",
          "C. NỢ PHẢI TRẢ 300 38.700 33.900",
          "I. Nợ ngắn hạn 310 28.100 24.700",
          "3. Phải trả người bán ngắn hạn 311 5.600 4.900",
          "10. Vay và nợ thuê tài chính ngắn hạn 320 V.15 10.600 9.100",
          "II. Nợ dài hạn 330 10.600 9.200",
          "8. Vay và nợ thuê tài chính dài hạn 338 5.700 4.800",
          "D. VỐN CHỦ SỞ HỮU 400 31.800 27.300",
          "1. Vốn góp của chủ sở hữu 411 12.700 12.700",
          "11. Lợi nhuận sau thuế chưa phân phối 421 11.200 9.300",
          "13. Lợi ích cổ đông không kiểm soát 429 2.600 2.200",
          "TỔNG CỘNG NGUỒN VỐN 440 70.500 61.200"])
    page(["BÁO CÁO KẾT QUẢ HOẠT ĐỘNG KINH DOANH HỢP NHẤT", unit_text,
          "CHỈ TIÊU Mã số Thuyết minh Năm 2025 Năm 2024",
          "1. Doanh thu bán hàng và cung cấp dịch vụ 01 VI.1 61.000 52.900",
          "3. Doanh thu thuần về bán hàng và cung cấp dịch vụ 10 60.300 52.400",
          "4. Giá vốn hàng bán 11 VI.2 (37.400) (32.600)",
          "5. Lợi nhuận gộp về bán hàng và cung cấp dịch vụ 20 22.900 19.800",
          "6. Doanh thu hoạt động tài chính 21 1.900 1.600",
          "7. Chi phí tài chính 22 (1.300) (1.100)",
          "Trong đó: Chi phí lãi vay 23 (720) (650)",
          "9. Chi phí bán hàng 25 (5.200) (4.500)",
          "10. Chi phí quản lý doanh nghiệp 26 (6.800) (6.000)",
          "11. Lợi nhuận thuần từ hoạt động kinh doanh 30 11.500 9.800",
          "15. Tổng lợi nhuận kế toán trước thuế 50 11.700 9.900",
          "16. Chi phí thuế TNDN hiện hành 51 (2.000) (1.700)",
          "18. Lợi nhuận sau thuế thu nhập doanh nghiệp 60 9.700 8.200",
          "18.1 Lợi nhuận sau thuế của cổ đông công ty mẹ 61 8.100 6.900",
          "19. Lãi cơ bản trên cổ phiếu (đồng) 70 VI.8 5.986 5.098"])
    page(["BÁO CÁO LƯU CHUYỂN TIỀN TỆ HỢP NHẤT", unit_text,
          "1. Lợi nhuận trước thuế 01 11.700 9.900",
          "Khấu hao TSCĐ và BĐSĐT 02 2.600 2.300",
          "Lưu chuyển tiền thuần từ hoạt động kinh doanh 20 11.900 10.100",
          "1. Tiền chi để mua sắm, xây dựng TSCĐ và các tài sản dài hạn khác 21 (4.100) (3.700)",
          "Lưu chuyển tiền thuần từ hoạt động đầu tư 30 (6.200) (5.300)",
          "6. Cổ tức, lợi nhuận đã trả cho chủ sở hữu 36 (2.500) (2.500)",
          "Lưu chuyển tiền thuần từ hoạt động tài chính 40 (3.600) (3.100)",
          "THUYẾT MINH BÁO CÁO TÀI CHÍNH HỢP NHẤT",
          "Doanh thu thuần 10 999.999"])
    return bytes(pdf.output())
