# REMEMBER.md — نکات مهم پروژه JGPTi

## تصمیمات کلیدی
- **سیستم پرامپت** باید از توی دیتابیس ست بشه، نه از توی کد
- **دیتابیس** همه چیز رو ذخیره کنه — هیچ چیزی in-memory نباشه
- **همزمانی** — باید چند یوزر همزمان بتونن چت کنن بدون صف شدن
- **یوزرها** — هر یوزر جدید اسم بده و توی DB ذخیره بشه
- **مدل انتخاب شده** — توی DB ذخیره بشه نه حافظه

## تغییرات لازم
- [x] System prompt در دیتابیس
- [x] پنل ادمین: نمایش/ویرایش سیستم پرامپت
- [x] Concurrent user handling
- [x] User onboarding (اسم بپرسه)
- [x] اسم یوزر توی system prompt مدل

## My Development Experience (opencode)

### Startup Commands
- **Backend:** `cd backend && source venv/bin/activate && uvicorn app.main:app --host 0.0.0.0 --port 8000`
- **Telegram/Bale Bot:** `cd backend && source venv/bin/activate && python -m app.bot`
- **Frontend (Admin Panel):** `cd frontend-v2 && npm run dev -- --host 0.0.0.0 --port 3000`

### Key Fixes Applied
1. **Vision Support:** Resolved issues where images (both photos and documents) were not reaching the AI models. Improved model capability detection and message tagging.
2. **Bot Persistence:** Fixed a bug where bot updates would get stuck in "processing". Added completion acknowledgement to all handlers.
3. **Automated Starter Credit:** Fixed the system to automatically grant new users their starter credit (e.g., $0.07) upon signup.
4. **Admin Panel Stability:** Fixed a Pydantic schema mismatch that caused the model list to crash when providers were missing.
5. **Upload Logic:** Refined file handling so that only files uploaded specifically through the "Project Upload" menu are embedded for RAG; normal chat uploads remain as conversation context.

### Deployment Note
In this environment, use `setsid` to ensure services remain running in the background:
```bash
# Backend
cd backend && setsid venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000 >> backend.log 2>&1 &
# Bot
cd backend && setsid venv/bin/python3 -u -m app.bot >> bot_persistent.log 2>&1 &
# Frontend
cd frontend-v2 && setsid npm run dev -- --host 0.0.0.0 --port 3000 >> frontend.log 2>&1 &
```
