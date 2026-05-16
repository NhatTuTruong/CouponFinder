# Hướng dẫn chạy source (Coupon Finder)

Tài liệu ngắn gọn để clone repo và chạy được tool. Chi tiết cấu hình collector (Apify, SerpAPI, Google CSE) xem thêm [README.md](README.md).

## Yêu cầu

- **Python ≥ 3.11** (theo `pyproject.toml`)
- Windows: PowerShell hoặc CMD; Git Bash có thể dùng `source .venv/Scripts/activate`

## Cài đặt lần đầu

Mở terminal tại **thư mục gốc project** (cùng cấp với `pyproject.toml`).

### PowerShell / CMD

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -U pip
python -m pip install -e .
python -m playwright install chromium
```

### Git Bash

```bash
python -m venv .venv
source .venv/Scripts/activate
python -m pip install -U pip
python -m pip install -e .
python -m playwright install chromium
```

## File `.env`

1. Sao chép `.env.example` → `.env` (đặt **cạnh** `pyproject.toml`).
2. Điền ít nhất **một** nguồn nếu muốn tìm trên web: `COUPON_FINDER_APIFY_TOKEN`, hoặc `COUPON_FINDER_SERPAPI_KEY`, hoặc cặp Google CSE (`COUPON_FINDER_GOOGLE_API_KEY` + `COUPON_FINDER_GOOGLE_CSE_ID`).
3. Chỉ thử nhanh **không tốn API / không verify**: có thể dùng `--no-verify` và dữ liệu file cộng đồng (xem README).

## Kiểm tra môi trường

```powershell
python -m coupon_finder.cli doctor
```

Nếu cần log chi tiết khi lỗi:

```powershell
$env:COUPON_FINDER_DEBUG="true"
python -m coupon_finder.cli doctor
```

(Git Bash: `export COUPON_FINDER_DEBUG=true`)

## Chạy CLI

Luôn **bật venv** trước (`Activate.ps1` hoặc `source ...`).

### Tìm coupon (ví dụ không verify — nhanh)

```powershell
python -m coupon_finder.cli search-cmd --brand "DemoBrand" --website "https://example.com" --no-verify
```

### Tìm có verify Playwright (chậm hơn, mở Chromium)

```powershell
python -m coupon_finder.cli search-cmd --brand "Nike" --website "https://www.nike.com" --limit-verify 5
```

### Xem mã đã lưu trong SQLite

```powershell
python -m coupon_finder.cli list-cmd --brand "Nike" --website "https://www.nike.com" --all --limit 50
```

### Cách gọi tương đương (nếu có trong PATH)

```powershell
coupon-finder search-cmd --brand "Nike" --website "https://www.nike.com" --product "Air Force 1"
```

Dữ liệu SQLite mặc định: `./data/coupons.db`.

## Chạy API và giao diện web

```powershell
coupon-finder api --host 127.0.0.1 --port 8000
```

Hoặc:

```powershell
python -m coupon_finder.cli api --host 127.0.0.1 --port 8000
```

- UI: http://127.0.0.1:8000/
- Swagger: http://127.0.0.1:8000/docs

## Ghi chú về “source” trong `coupon_finder/sources/`

Các file như `coupon_finder/sources/simply_codes.py` là **module collector** được pipeline gọi khi chạy `search-cmd` / API. Không cần chạy trực tiếp từng file trừ khi bạn tự viết script import — luồng chuẩn là **CLI hoặc API** như trên.

## Đóng gói app `.exe` (desktop)

App desktop chạy server FastAPI nội bộ và mở cửa sổ Chrome/Edge (chế độ `--app`), **không** cần chạy `coupon-finder api` hay mở trình duyệt thủ công.

### Yêu cầu build

- Windows, Python ≥ 3.11, venv đã cài project (`pip install -e .`)
- Cùng máy đã chạy được `python -m coupon_finder.cli doctor` (tùy chọn nhưng nên kiểm tra trước khi đóng gói)

### Cách build (chọn một)

**Cách 1 — file `.cmd` (khuyến nghị, không bị chặn Execution Policy):**

```cmd
build_exe.cmd
```

Hoặc trong PowerShell:

```powershell
.\build_exe.cmd
```

**Cách 2 — script PowerShell:**

```powershell
.\build_exe.ps1
```

Nếu báo *running scripts is disabled*, dùng **Cách 1** hoặc một trong các lệnh sau:

```powershell
powershell -ExecutionPolicy Bypass -File .\build_exe.ps1
```

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

(chỉ cần chạy `Set-ExecutionPolicy` một lần trên máy)

**Cách 3 — lệnh CLI:**

```powershell
.\.venv\Scripts\Activate.ps1
pip install -e ".[build-exe]"
python -m coupon_finder.cli build-exe
```

Giữ lại thư mục `dist` cũ (vd. file `.env` đã copy vào `dist`):

```powershell
python -m coupon_finder.cli build-exe --no-clean
```

**Cách 4 — PyInstaller trực tiếp:**

```powershell
pip install -e ".[build-exe]"
python -m PyInstaller --noconfirm CouponFinder.spec
```

### Kết quả build

| Thành phần | Đường dẫn |
|------------|-----------|
| File chạy | `dist\CouponFinder.exe` |
| Cấu hình build | `CouponFinder.spec` |
| Thư mục tạm PyInstaller | `build\` (có thể xóa sau build) |

Mặc định `build-exe` **xóa** `build\` và `dist\` trước khi đóng gói (`--clean`). Nếu bạn đã đặt `.env` trong `dist\`, hãy dùng `--no-clean` hoặc copy lại `.env` sau build.

### Phân phối / chạy trên máy khác

1. Copy `CouponFinder.exe` sang thư mục làm việc (vd. `D:\CouponFinder\`).
2. Đặt file `.env` **cùng thư mục** với `CouponFinder.exe` (sao từ `.env.example` rồi điền token).
3. Double-click `CouponFinder.exe`.
4. Cần **Google Chrome** hoặc **Microsoft Edge** trên máy (app mở cửa sổ riêng). Nếu dùng Playwright scrape, cài Chromium: `playwright install chromium` trên máy dev; máy người dùng chỉ cần Chrome/Edge nếu `.env` có `COUPON_FINDER_PLAYWRIGHT_CHANNEL=chrome`.

**Khi chạy `.exe`:**

- Server nội bộ: `http://127.0.0.1:8765/` (đổi cổng: biến môi trường `COUPON_FINDER_PORT`).
- Thư mục `data\` (SQLite `coupons.db`, lịch sử JSON, log) tạo **cạnh** file `.exe`.
- Tab **Cài đặt** trong UI vẫn sửa được `.env` cạnh exe.

### Xử lý lỗi khi mở `.exe`

| Triệu chứng | Gợi ý |
|-------------|--------|
| «Không khởi động được server…» / cổng 8765 | Đóng instance `CouponFinder.exe` cũ hoặc tiến trình đang chiếm cổng; thử `COUPON_FINDER_PORT=8770` |
| Cửa sổ báo lỗi chi tiết | Xem `data\coupon_finder_startup.log` và `data\coupon_finder_console.log` cạnh file `.exe` |
| Build báo *Access is denied* / `WinError 5` trên `dist\CouponFinder.exe` | Đóng mọi cửa sổ app (có thể còn nhiều process nền). `taskkill /IM CouponFinder.exe /F` rồi build lại; `build_exe.cmd` / `build-exe` tự thử đóng trước khi đóng gói |

### Build lại sau khi sửa code

```cmd
build_exe.cmd
```

Hoặc từ repo (đã bật venv):

```powershell
python -m coupon_finder.cli build-exe --no-clean
```

## Server license (Laravel)

Tool **bắt buộc** có mã license hợp lệ mới tìm được coupon.

### Chạy server license (MySQL)

1. Tạo database: `CREATE DATABASE coupon_finder_license CHARACTER SET utf8mb4;`
2. Cấu hình `license-server/.env` (`DB_*` — mặc định MySQL, DB `coupon_finder_license`).
3. Migrate và chạy:

```powershell
cd license-server
php artisan migrate
php artisan serve --host=127.0.0.1 --port=8080
```

Trang admin: http://127.0.0.1:8080/admin/login — mật khẩu trong `license-server/.env` (`ADMIN_PASSWORD`, mặc định `123456`).

Sau đăng nhập: quản lý license — tạo key mới hoặc **sửa trực tiếp trong danh sách** rồi bấm **Lưu**.

Chi tiết: [license-server/README.md](license-server/README.md)

### Cấu hình tool

Trong `.env` (hoặc tab **Cài đặt**):

```
COUPON_FINDER_LICENSE_SERVER_URL=http://127.0.0.1:8080
COUPON_FINDER_LICENSE_KEY=MA-LICENSE-TU-ADMIN
```

Không nhập mã → nút **Tìm coupon** bị khóa.

## Tham chiếu

- Cấu hình đầy đủ biến môi trường, collector, robots/ToS: [README.md](README.md)
