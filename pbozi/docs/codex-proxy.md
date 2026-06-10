# Codex Proxy - مستندات کامل

## خلاصه

Codex Proxy یک endpoint OpenAI-compatible است که درخواست‌های چت را به Codex CLI تبدیل می‌کند. این به ما اجازه می‌دهد اشتراک $20 ماهانه Codex را بین چندین کاربر به اشتراک بگذاریم و حاشیه سود ۸۰-۹۰٪ داشته باشیم.

## معماری

```
┌─────────────┐     OpenAI API      ┌──────────────────┐     Codex CLI      ┌─────────────┐
│  Frontend   │ ──────────────────► │  Codex Proxy     │ ─────────────────► │  Codex CLI  │
│  (Chat UI)  │   /v1/chat/         │  /codex-proxy/   │   stdin/stdout    │  (local)    │
│             │ ◄────────────────── │  v1/             │ ◄───────────────── │             │
└─────────────┘   SSE / JSON        └──────────────────┘   JSON events      └─────────────┐
                                                                                │
                                                                                │ Account selection
                                                                                ▼
                                                                        ┌─────────────┐
                                                                        │   Codex     │
                                                                        │  Accounts   │
                                                                        │  (multi)    │
                                                                        └─────────────┘
```

## Endpoint‌ها

### API اصلی

| Method | Path | توضیح |
|--------|------|-------|
| `POST` | `/codex-proxy/v1/chat/completions` | درخواست چت (OpenAI-compatible) |

### پنل ادمین

| Method | Path | توضیح |
|--------|------|-------|
| `GET` | `/api/admin/codex-proxy/requests` | لیست درخواست‌ها |
| `GET` | `/api/admin/codex-proxy/requests/{id}` | جزئیات یک درخواست |
| `GET` | `/api/admin/codex-proxy/stats` | آمار مصرف |
| `GET` | `/api/admin/codex-proxy/accounts` | لیست اکانت‌های Codex |

## تنظیمات در پنل ادمین

### ۱. ساخت Provider جدید

در پنل ادمین → Providers:

- **Name**: `Codex Proxy`
- **Base URL**: `http://localhost:7000/codex-proxy/v1`
- **Kind**: `openai_compatible`
- **API Key**: `dummy` (هر مقداری کار می‌کند)

### ۲. اضافه کردن مدل‌ها

زیر provider جدید، مدل‌های مورد نظر را اضافه کنید:

| Model Name | Display Name | Capabilities |
|------------|-------------|--------------|
| `gpt-5.4` | GPT-5.4 Pro | `{"image_input": true}` |
| `gpt-5.3-codex` | GPT-5.3 Pro | `{"image_input": true}` |
| `gpt-5.4-mini` | GPT-5.4 Mini | `{"image_input": true}` |

### ۳. انتخاب مدل در چت

کاربران می‌توانند این مدل‌ها را مثل هر مدل API دیگری انتخاب کنند.

## قابلیت‌های پشتیبانی شده

### ✅ تصاویر (Vision)
تصاویر به صورت base64 در درخواست ارسال می‌شوند و proxy آن‌ها را به فایل‌های موقت تبدیل کرده و با فلگ `--image` به Codex CLI می‌دهد.

```json
{
  "model": "gpt-5.4",
  "messages": [{
    "role": "user",
    "content": [
      {"type": "text", "text": "What is in this image?"},
      {"type": "image_url", "image_url": {"url": "data:image/png;base64,..."}}
    ]
  }]
}
```

### ✅ Streaming (SSE)
پشتیبانی کامل از Server-Sent Events برای پاسخ‌های استریمینگ:

```json
{
  "model": "gpt-5.4",
  "messages": [{"role": "user", "content": "Hello"}],
  "stream": true
}
```

### ✅ فایل‌ها
فایل‌هایی که به صورت text در messages باشند پشتیبانی می‌شوند.

### ✅ Usage Tracking
توکن‌های مصرفی (input, output, total) به صورت خودکار ثبت می‌شود.

## پنل ادمین - API‌ها

### لیست درخواست‌ها

```
GET /api/admin/codex-proxy/requests?limit=50&offset=0&model=gpt-5.4&status=success&has_image=true
```

فیلترها:
- `limit` (پیش‌فرض: 50)
- `offset` (پیش‌فرض: 0)
- `model` - فیلتر بر اساس مدل
- `status` - `success` یا `error`
- `account_id` - فیلتر بر اساس اکانت
- `has_image` - `true` یا `false`
- `date_from` / `date_to` - فیلتر زمانی (ISO format)

### آمار مصرف

```
GET /api/admin/codex-proxy/stats?hours=24
```

خروجی:
```json
{
  "period_hours": 24,
  "total_requests": 150,
  "success_requests": 145,
  "error_requests": 5,
  "total_tokens": 2500000,
  "prompt_tokens": 2000000,
  "completion_tokens": 500000,
  "avg_duration_ms": 4500.0,
  "image_requests": 30,
  "by_model": [
    {"model": "gpt-5.4", "requests": 100, "total_tokens": 1800000},
    {"model": "gpt-5.4-mini", "requests": 50, "total_tokens": 700000}
  ],
  "by_account": [
    {"account_id": 1, "requests": 80, "total_tokens": 1200000},
    {"account_id": 2, "requests": 70, "total_tokens": 1300000}
  ]
}
```

### لیست اکانت‌های Codex

```
GET /api/admin/codex-proxy/accounts
```

خروجی شامل اطلاعات هر اکانت: label, auth_status, limits, usage, last_error

## دیتابیس

### جدول `codex_proxy_request_logs`

| ستون | نوع | توضیح |
|------|-----|-------|
| `id` | Integer | Primary key |
| `request_id` | String | UUID یکتا برای هر درخواست |
| `model` | String | نام مدل استفاده شده |
| `account_id` | Integer | اکانت Codex استفاده شده |
| `status` | String | `success` یا `error` |
| `prompt_tokens` | Integer | توکن‌های ورودی |
| `completion_tokens` | Integer | توکن‌های خروجی |
| `total_tokens` | Integer | مجموع توکن‌ها |
| `duration_ms` | Integer | مدت زمان پاسخ (میلی‌ثانیه) |
| `has_image` | Boolean | آیا تصویر داشت |
| `image_count` | Integer | تعداد تصاویر |
| `error_message` | Text | پیام خطا (در صورت وجود) |
| `created_at` | DateTime | زمان درخواست |

## مدیریت اکانت‌های Codex

سیستم به صورت خودکار بین اکانت‌های Codex موجود انتخاب می‌کند (بر اساس availability و cooldown). اکانت‌ها در جدول `codex_accounts` مدیریت می‌شوند.

### محدودیت‌ها

- `five_hour_limit` / `five_hour_used`: محدودیت ۵ ساعته
- `weekly_limit` / `weekly_used`: محدودیت هفتگی
- `cooldown_until`: زمان پایان cooldown پس از رسیدن به محدودیت

## عیب‌یابی

### خطای "No authenticated Codex account available"
- بررسی کنید اکانت‌های Codex فعال و authenticated باشند
- `codex login status` را در هر اکانت چک کنید

### خطای "Codex CLI timed out"
- timeout پیش‌فرض ۱۲۰ ثانیه است
- با env var `CODEX_EXEC_TIMEOUT_SECONDS` قابل تنظیم است

### خطای تصویر
- تصاویر باید base64-encoded باشند
- فرمت‌های پشتیبانی شده: JPEG, PNG, WebP, GIF
- حداکثر سایز: محدودیت Codex CLI

## فایل‌های مرتبط

| فایل | توضیح |
|------|-------|
| `backend/app/codex_proxy.py` | endpoint اصلی proxy |
| `backend/app/admin_codex_proxy_routes.py` | API‌های پنل ادمین |
| `backend/app/models.py` | مدل `CodexProxyRequestLog` |
| `backend/app/services/codex_runtime.py` | توابع مشترک Codex |
