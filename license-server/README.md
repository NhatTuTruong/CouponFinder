# Coupon Finder — License Server (Laravel + MySQL)

Server quản lý mã bản quyền cho tool Coupon Finder.

## Yêu cầu

- PHP ≥ 8.2, Composer
- **MySQL** (MariaDB) — ví dụ WAMP/XAMPP

## Cài đặt

### 1. Tạo database MySQL

```sql
CREATE DATABASE coupon_finder_license
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;
```

### 2. Cấu hình `.env`

```env
DB_CONNECTION=mysql
DB_HOST=127.0.0.1
DB_PORT=3306
DB_DATABASE=coupon_finder_license
DB_USERNAME=root
DB_PASSWORD=          # mật khẩu MySQL của bạn
```

### 3. Migrate & chạy

```bash
cd license-server
composer install   # lần đầu
php artisan key:generate   # lần đầu
php artisan migrate
php artisan serve --host=127.0.0.1 --port=8080
```

Trang đăng nhập: http://127.0.0.1:8080/admin/login

Mật khẩu mặc định trong `.env`: `ADMIN_PASSWORD=123456` (đổi trước khi deploy production).

Sau đăng nhập: http://127.0.0.1:8080/admin/licenses

## Quản lý license

- **Thêm mới:** form phía trên (key, giới hạn/ngày, số máy, hạn, ghi chú).
- **Sửa:** chỉnh trực tiếp trong **Danh sách license** → bấm **Lưu** trên từng dòng.
- Cột **Đã dùng hôm nay** = số lượt tìm đã trừ trong ngày.

## API cho tool

Base URL: `http://127.0.0.1:8080`

| Method | Endpoint | Mô tả |
|--------|----------|--------|
| POST | `/api/v1/license/activate` | Đăng ký máy |
| POST | `/api/v1/license/status` | Kiểm tra quota |
| POST | `/api/v1/license/consume` | Trừ lượt tìm |

## Cấu hình tool

```
COUPON_FINDER_LICENSE_SERVER_URL=http://127.0.0.1:8080
COUPON_FINDER_LICENSE_KEY=MA-LICENSE-TU-ADMIN
```

## Chuyển từ SQLite sang MySQL

Nếu trước đó dùng SQLite, export dữ liệu thủ công hoặc tạo lại license trên MySQL. Đổi `DB_CONNECTION=mysql` trong `.env` rồi `php artisan migrate`.
