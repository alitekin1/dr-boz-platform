# 📋 پلن پروژه JGPTi

## خلاصه
اپ AI چت با RAG، مدیریت پروژه، و ادمین میتونه خودش پروایدر OpenAI-compatible اضافه کنه + مدل + قیمت

## تکنولوژی (سریع‌ترین)
- **بک‌اند:** Python FastAPI ⚡
- **فرانت:** Next.js + Tailwind CSS
- **دیتابیس:** SQLite (ساده، سریع)
- **وکتور دیتابیس:** ChromaDB (لوکال، بدون نیاز به سرویس اضافه)
- **LLM:** OpenAI-compatible API (ادمین پروایدر اضافه میکنه)

## فاز ۱: بک‌اند هسته 🏗️
- [x] FastAPI پروژه ✅
- [x] دیتابیس SQLAlchemy + SQLite ✅
- [x] API endpoints ✅
- [x] پروایدر/مدل CRUD ✅
- [x] چت + پیام ✅
- [x] RAG (ChromaDB) ✅
- [x] Title Generator ✅
- [x] آپلود فایل ✅
- [x] تلگرام بات ✅
- [ ] مدل‌های دیتابیس (SQLAlchemy + SQLite):
  - Provider (name, base_url, api_key, is_active)
  - Model (name, provider_id, pricing_input, pricing_output, is_active)
  - Project (name, description, created_at)
  - Chat (project_id, title, created_at)
  - Message (chat_id, role, content, created_at)
  - Document (project_id, filename, file_type, created_at)
- [ ] API endpoints:
  - `/admin/providers` — CRUD پروایدرها
  - `/admin/models` — CRUD مدل‌ها + قیمت‌گذاری
  - `/chats` — لیست، ایجاد، حذف
  - `/chats/{id}/messages` — ارسال پیام و دریافت جواب
  - `/projects` — CRUD پروژه‌ها
  - `/projects/{id}/documents` — آپلود فایل

## فاز ۲: چت با AI 💬
- [ ] ارسال پیام → فراخوانی مدل (OpenAI-compatible)
- [ ] Title Generator خودکار (از پرامپت داده شده)
- [ ] انتخاب پروژه برای چت
- [ ] استریم جواب

## فاز ۳: RAG 📚
- [ ] آپلود PDF/TXT/MD
- [ ] Chunking + Embedding (با مدل ادمین)
- [ ] ذخیره توی ChromaDB
- [ ] Retrieval: سرچ وکتوری + فراخوانی مدل با کانتکست

## فاز ۴: تلگرام بات 🤖
- [ ] Bot token: `8475490294:AAGp6SdaC1KYWfTA76Rl5maw1y58Jg9dRzk`
- [ ] python-telegram-bot
- [ ] همون قابلیت‌ها از تلگرام
- [ ] Title Generator خودکار

## فاز ۵: فرانت‌اند 🎨
- [x] Next.js + Tailwind ✅
- [x] صفحه چت ✅
- [x] صفحه ادمین (پروایدر + مدل) ✅
- [ ] صفحه پروژه‌ها + آپلود

## فاز ۶: دیپلوی 🚀
- [ ] Docker
- [ ] تست
- [ ] دیپلوی

---

## پرامپت Title Generator
```
### Task:
Generate a concise, 3-5 word title with an emoji summarizing the chat history.
### Guidelines:
- The title should clearly represent the main theme or subject of the conversation.
- Use emojis that enhance understanding of the topic, but avoid quotation marks or special formatting.
- Write the title in the chat's primary language; default to English if multilingual.
- Prioritize accuracy over excessive creativity; keep it clear and simple.
- The output must be any markdown code fences or other encapsulating text.
- Ensure no conversational text, affirmations, or explanations precede or follow the raw JSON output, as this will cause direct parsing failure.
### Output:
your concise title here
```

---

*آپدیت: 2026-04-20*
