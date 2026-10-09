# Lấy dữ liệu báo cáo tài chính & chỉ số tài chính (HSX/HNX)

```powershell
python -m pip install -r requirements.txt
python fetch_financials.py VNM HPG      # hoặc không kèm mã để nhập tương tác
```
Kết quả: `output/<MÃ>_financials.xlsx` (Thông tin, 3 báo cáo, Chỉ số tài chính, Ánh xạ biến) + CSV từng báo cáo.

Dùng trong code nhóm:
```python
from fetch_financials import get_financials
from ratios import get_ratios
d = get_financials("VNM")      # d["balance_sheet"] | d["income_statement"] | d["cash_flow"] (dòng = chỉ tiêu, cột = năm)
r = get_ratios(d)              # r["ratios"] (dòng = năm), r["mapping"] (chỉ tiêu dataset được dùng)
```
Nguồn dữ liệu: gói `vnfinancialdata` (Ngo Phu Thanh, UEL), dataset v1.0.0, schema 1.0; chỉ HSX/HNX, dữ liệu theo năm.
Đơn vị giữ nguyên như dataset — cần tự kiểm tra với BCTC gốc. Test: `python -m pytest -q` (dữ liệu giả lập).
