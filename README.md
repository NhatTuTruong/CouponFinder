# Coupon Finder (Python)

Tool tìm coupon theo quy trình:
thu thập nhiều nguồn → làm sạch/chuẩn hoá → **verify trực tiếp trên website** → phân loại → chấm điểm → theo dõi/cập nhật → trả kết quả.

## Cài đặt (Windows)

**PowerShell / CMD**

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -U pip
python -m pip install -e .
python -m playwright install chromium
```

**Git Bash (MINGW64)** — không dùng dấu `\` cho `activate`; dùng `source`:

```bash
python -m venv .venv
source .venv/Scripts/activate
python -m pip install -U pip
python -m pip install -e .
python -m playwright install chromium
```

## File `.env` và test nhanh

1. Sao chép `.env.example` → `.env` (hoặc sửa file `.env` đã có trong repo).
2. Điền ít nhất **một** nguồn: `COUPON_FINDER_APIFY_TOKEN`, hoặc `COUPON_FINDER_SERPAPI_KEY`, hoặc cặp Google CSE.
3. File **`.env` đặt cạnh `pyproject.toml`** (thư mục gốc project). Tool sẽ đọc file đó **dù bạn chạy CLI từ thư mục khác**; nếu không có `.env` ở gốc project, sẽ thử file `.env` trong thư mục hiện tại.

**Không tốn Apify / Playwright** (chỉ file cộng đồng + làm sạch):

```bash
cd "/d/Project/Tool Tìm Coupon"
source .venv/Scripts/activate
python -m coupon_finder.cli search-cmd --brand "DemoBrand" --website "https://example.com" --no-verify
```

**Chẩn đoán môi trường** (đường dẫn `.env`, key đã nạp — không in token; có thử `collect_all` Nike):

```bash
python -m coupon_finder.cli doctor
```

Nếu Apify lỗi mà không thấy chi tiết, bật log traceback rồi chạy lại `doctor` hoặc `search-cmd`:

```bash
export COUPON_FINDER_DEBUG=true
python -m coupon_finder.cli doctor
```

**Có Apify** (điền token trong `.env` trước; tốn compute Apify):

```bash
cd "/d/Project/Tool Tìm Coupon"
source .venv/Scripts/activate
python -m coupon_finder.cli search-cmd --brand "Nike" --website "https://www.nike.com" --no-verify
```

**Verify bằng Playwright** (chậm hơn, mở Chromium):

```bash
python -m coupon_finder.cli search-cmd --brand "Nike" --website "https://www.nike.com" --limit-verify 5
```

## Chạy CLI

Sau khi bật venv, dùng một trong hai cách (nếu `coupon-finder` không nằm trong PATH, dùng `python -m ...`):

```bash
coupon-finder search-cmd --brand "Nike" --website "https://www.nike.com" --product "Air Force 1"
```

```bash
python -m coupon_finder.cli search-cmd --brand "Nike" --website "https://www.nike.com" --product "Air Force 1"
```

Xem trước mã **chưa verify** (nhanh, không mở trình duyệt): thêm `--no-verify`.

- Với **`--verify` (mặc định)**: CLI in **hai phần** — bảng **COLLECTED** (tối đa 100 mã sau chuẩn hoá) rồi bảng **sau Playwright verify**.
- **`list-cmd`**: xem mã đã ghi trong SQLite (sau các lần search trước):

```bash
python -m coupon_finder.cli list-cmd --brand "Nike" --website "https://www.nike.com" --all --limit 50
```

Kết quả sẽ được lưu vào SQLite tại `./data/coupons.db`.

## Chạy API

```bash
coupon-finder api --host 127.0.0.1 --port 8000
```

Mở docs tại `http://127.0.0.1:8000/docs`.

### Giao diện web (UI)

1. Chạy API như trên.
2. Mở trình duyệt: **`http://127.0.0.1:8000/`** (trang tĩnh trong `coupon_finder/web_public/`).
3. Nhập **domain** (vd `nike.com`) → **Tìm coupon** → chọn mã trong bảng → **Verify đã chọn** (gọi `POST /api/ui/verify`, Playwright thử từng mã trên website đã suy ra từ domain).

API JSON: `POST /api/ui/search` `{ "domain": "nike.com" }` · `POST /api/ui/verify` `{ "domain": "...", "codes": ["SAVE10"] }`.

## Gửi coupon cộng đồng (nguồn nội bộ)

Bạn có thể thêm coupon thủ công vào `data/community_coupons.json` (có mẫu sẵn), tool sẽ coi như nguồn “cộng đồng người dùng”.

**Lưu ý (file cộng đồng):** Các dòng trong `community_coupons.json` phải khớp `brand` và `website` (cùng tên miền) với lệnh search. Nếu không cấu hình tìm kiếm bên ngoài bên dưới, mà file lại không có brand đó thì kết quả sẽ rỗng.

## Tìm coupon từ bên ngoài (web)

**Không bắt buộc** phải có dịch vụ thứ ba: bạn có thể chỉ dùng file JSON + **Playwright** (đã có trong project) để verify trên site. Nhưng để **tự động khám phá** trang/mã trên internet (thay vì nhập tay), thực tế thường cần **một trong các hướng sau**:

| Cách | Ghi chú ngắn |
|------|----------------|
| **API tìm kiếm** (khuyến nghị khi cần quy mô) | [SerpAPI](https://serpapi.com/), [Google Programmable Search](https://developers.google.com/custom-search/v1/overview), Bing Web Search API… — trả JSON, ổn định hơn tự scrape Google HTML. |
| **Crawl từng site coupon** | `requests` + BeautifulSoup hoặc **Playwright** cho trang render JS; phải tuân **robots.txt / ToS** từng site. |
| **Feed / API chính thức** | Một số mạng affiliate có feed; ít site “coupon” cho API công khai miễn phí. |

Project đã tích hợp **các collector tùy chọn** (bật khi có biến môi trường):

1. **SerpAPI** — gửi truy vấn Google organic, đọc title/snippet, trích các chuỗi giống mã coupon (heuristic).
2. **Google Custom Search JSON API** — tương tự, cần API key + **Search engine ID (cx)**.
3. **Apify** — chạy Actor (mặc định `nFJndFXA5zjCTuudP`, có thể đổi), đọc dataset kết quả tìm kiếm / trang liên quan, trích mã. Tool tự ghép thêm các truy vấn dạng `site:retailmenot.com {brand} coupon` (danh sách domain cấu hình được qua `COUPON_FINDER_APIFY_COUPON_SITE_DOMAINS`) để hướng tới **một số trang coupon lớn** qua Google, không crawl trực tiếp vào HTML của họ (tránh phải duy trì parser từng site — vẫn cần tuân luật Google/Apify và điều khoản từng bên).

Tạo file `.env` ở root project (hoặc export biến môi trường), prefix `COUPON_FINDER_`:

```env
# Bật 1 trong 2 (hoặc cả hai — sẽ gộp kết quả, có thể trùng)
COUPON_FINDER_SERPAPI_KEY=...
COUPON_FINDER_GOOGLE_API_KEY=...
COUPON_FINDER_GOOGLE_CSE_ID=...
COUPON_FINDER_EXTERNAL_SEARCH_MAX_RESULTS=10

# Apify (đã có dependency apify-client)
COUPON_FINDER_APIFY_TOKEN=...
# COUPON_FINDER_APIFY_ACTOR_ID=nFJndFXA5zjCTuudP
# COUPON_FINDER_APIFY_MAX_PAGES_PER_QUERY=3
# COUPON_FINDER_APIFY_COUPON_SITE_DOMAINS=retailmenot.com,coupons.com,offers.com
# Merge thêm field vào input Actor (JSON một dòng hoặc nhiều dòng trong .env — khuyến nghị dùng file .env UTF-8)
# COUPON_FINDER_APIFY_RUN_INPUT_EXTRA_JSON={"enablePerplexity": true}
```

Mã lấy từ snippet **có thể sai** (false positive); bước verify Playwright trên `--website` giúp lọc phần nào đó.

