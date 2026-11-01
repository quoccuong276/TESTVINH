# Báo cáo đầu tư chứng khoán

Tự động lấy dữ liệu từ Google Sheet → lưu vào repo → sinh báo cáo HTML (GitHub Pages).

## Báo cáo gồm 3 góc nhìn
| Tab | Nội dung |
|---|---|
| **Thời gian** | Lãi lỗ theo tháng/tuần, đường lũy kế, số lệnh chốt theo tuần |
| **Cổ phiếu** | Lãi lỗ, tỷ lệ thắng, % TB/lệnh, nắm giữ TB từng mã; tỷ trọng và lãi lỗ tạm tính vị thế đang mở |
| **Thời gian nắm giữ** | Phân nhóm 1–2 / 3–7 / 8–14 / 15–21 / 22+ ngày; biểu đồ ngày giữ vs % lãi lỗ; theo lý do bán; Cash vs T7 |

## Cài đặt
1. Tạo repo GitHub, đẩy toàn bộ thư mục này lên.
2. Mở Google Sheet → **Chia sẻ → Bất kỳ ai có đường liên kết → Người xem** (script đọc qua link export CSV).
3. Repo → **Settings → Pages** → Source: *Deploy from a branch* → Branch `main`, thư mục `/docs`.
4. Repo → **Actions → Cập nhật báo cáo → Run workflow** để chạy lần đầu. Sau đó tự chạy mỗi ngày 08:00 (giờ VN).
5. Báo cáo ở `https://<user>.github.io/<repo>/`.

Chạy thử trên máy: `python build_report.py` rồi mở `docs/index.html`.

## Đổi sheet / tab khác
Sửa biến môi trường `SHEET_ID`, `SHEET_GID` (mặc định đã là sheet của bạn), hoặc đặt trong workflow:
```yaml
env:
  SHEET_ID: xxxxx
  SHEET_GID: 123456
```

## Quy ước tính toán
- Script tự tìm dòng tiêu đề có `Cổ phiếu` + `Ngày mua`, bỏ qua các dòng `#DIV/0!` / trống.
- **Lệnh đã đóng** = có ngày bán và KL bán > 0. Lãi lỗ lấy từ cột `Lãi lỗ` (đã trừ phí, thuế).
- **Thời gian nắm giữ** tự tính lại = ngày bán − ngày mua (đang mở: hôm nay − ngày mua), vì cột gốc trong sheet bị lỗi ở lệnh đang mở (ví dụ `-46310`).
- **Lệnh đang mở**: lãi lỗ tạm tính = (giá hiện tại − giá mua) × SL đang giữ, chưa trừ phí. Lệnh bán một phần chưa ghi ngày bán (như dòng VND 15/Oct) được coi là đang mở.
- Thắng = lãi lỗ > 0. Profit factor = tổng lãi / tổng lỗ.

## Cấu trúc
```
build_report.py                 # lấy CSV, phân tích, sinh HTML
template.html                   # giao diện báo cáo (Chart.js)
data/raw_sheet.csv trades.csv report.json   # dữ liệu lưu trong repo (lịch sử qua git)
docs/index.html                 # báo cáo cho GitHub Pages
.github/workflows/update-report.yml
```

> Nếu không muốn công khai sheet: dùng service account + Google Sheets API, đặt key vào GitHub Secrets (có thể bổ sung sau).
