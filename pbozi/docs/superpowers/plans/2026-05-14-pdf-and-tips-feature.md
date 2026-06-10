# PDF Export & TIPS Feature Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Allow users to convert AI responses to PDF and introduce a tooltip (TIPS) system to educate them about this feature.

**Architecture:** A Node.js Puppeteer script generates the PDF from Markdown + MathJax. Python triggers this script. The Telegram bot UI is updated to show a "Convert to PDF" button on AI messages and a temporary TIPS message for math-heavy responses.

**Tech Stack:** Node.js, Puppeteer, markdown-it, Python, python-telegram-bot, SQLAlchemy.

---

### Task 1: Update Database Schema

**Files:**
- Modify: `backend/app/models.py`
- Create: (N/A, auto-migration)

- [ ] **Step 1: Add column to UserPreference**

In `backend/app/models.py`, find the `UserPreference` class and add the following column before `created_at`:

```python
    tip_pdf_math_dismissed = Column(Boolean, default=False)
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/models.py
git commit -m "feat: add tip_pdf_math_dismissed to UserPreference"
```

### Task 2: Setup Node.js PDF Generator

**Files:**
- Modify: `backend/package.json`
- Create: `backend/gen_pdf.js`

- [ ] **Step 1: Install Node Dependencies**

```bash
cd backend && npm install puppeteer markdown-it markdown-it-mathjax3
```

- [ ] **Step 2: Create PDF Generation Script**

Create `backend/gen_pdf.js`:

```javascript
const puppeteer = require('puppeteer');
const MarkdownIt = require('markdown-it');
const mathjax3 = require('markdown-it-mathjax3');
const fs = require('fs');

const md = new MarkdownIt({ html: true }).use(mathjax3);

const inputPath = process.argv[2];
const outputPath = process.argv[3];

if (!inputPath || !outputPath) {
    console.error("Usage: node gen_pdf.js <input.md> <output.pdf>");
    process.exit(1);
}

const markdownContent = fs.readFileSync(inputPath, 'utf8');
const htmlContent = md.render(markdownContent);

// Auto-detect RTL if Persian/Arabic characters are present
const isRTL = /[\u0600-\u06FF]/.test(markdownContent);
const direction = isRTL ? 'rtl' : 'ltr';

const htmlTemplate = `
<!DOCTYPE html>
<html dir="${direction}">
<head>
    <meta charset="UTF-8">
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Vazirmatn:wght@400;700&display=swap');
        body {
            font-family: 'Vazirmatn', sans-serif;
            padding: 40px;
            font-size: 16px;
            line-height: 1.6;
        }
        pre {
            background-color: #f4f4f4;
            padding: 15px;
            border-radius: 5px;
            direction: ltr; /* Code blocks always LTR */
            overflow-x: auto;
        }
        code {
            font-family: monospace;
            direction: ltr;
        }
    </style>
</head>
<body>
    ${htmlContent}
</body>
</html>
`;

(async () => {
    const browser = await puppeteer.launch({ args: ['--no-sandbox'] });
    const page = await browser.newPage();
    await page.setContent(htmlTemplate, { waitUntil: 'networkidle0' });
    await page.pdf({ path: outputPath, format: 'A4', printBackground: true });
    await browser.close();
})();
```

- [ ] **Step 3: Commit**

```bash
git add backend/package.json backend/package-lock.json backend/gen_pdf.js
git commit -m "feat: setup Node.js PDF generator with markdown and mathjax"
```

### Task 3: Python PDF Service Wrapper

**Files:**
- Create: `backend/app/services/pdf_export.py`

- [ ] **Step 1: Create the Python Service**

Create `backend/app/services/pdf_export.py`:

```python
import os
import subprocess
import tempfile
import uuid

async def generate_pdf_from_markdown(markdown_text: str) -> str:
    """Generates a PDF and returns the path to the generated file."""
    # Ensure backend directory is the working directory for node
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    
    with tempfile.NamedTemporaryFile(suffix=".md", delete=False, mode='w', encoding='utf-8') as md_file:
        md_file.write(markdown_text)
        md_path = md_file.name

    output_path = os.path.join(tempfile.gettempdir(), f"export_{uuid.uuid4().hex}.pdf")
    
    try:
        process = subprocess.run(
            ["node", "gen_pdf.js", md_path, output_path],
            cwd=base_dir,
            capture_output=True,
            text=True,
            check=True
        )
    except subprocess.CalledProcessError as e:
        if os.path.exists(md_path):
            os.remove(md_path)
        raise RuntimeError(f"PDF Generation failed: {e.stderr}")
        
    os.remove(md_path)
    return output_path
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/services/pdf_export.py
git commit -m "feat: add Python service to trigger PDF generation"
```

### Task 4: Bot UI - Convert to PDF Button

**Files:**
- Modify: `backend/app/bot.py`

- [ ] **Step 1: Update AI Response Keyboard**

In `backend/app/bot.py`, locate where the final AI message is sent or finalized. It often involves building an `InlineKeyboardMarkup`. Ensure the final message structure appends a button:
`InlineKeyboardButton("📄 تبدیل به PDF", callback_data=f"pdf_export")`.
*(Note for subagent: Search for the final chunk/message streaming logic where `reply_markup` is set for the AI response. If you cannot extract the specific message ID, you can use `callback_data="pdf_export"` and fetch the message text from `update.callback_query.message.text`)*.

- [ ] **Step 2: Handle PDF Callback**

In `backend/app/bot.py`, add a callback handler logic inside the main callback router (often `button_handler` or similar):

```python
# Import at the top
from app.services.pdf_export import generate_pdf_from_markdown
import os

# Inside your callback handler function:
if query.data == "pdf_export":
    await query.answer("در حال ساخت PDF...")
    sent_msg = await query.message.reply_text("⏳ در حال ساخت فایل...")
    try:
        # Get text from the message where the button is attached
        md_text = query.message.text or query.message.caption or ""
        pdf_path = await generate_pdf_from_markdown(md_text)
        
        with open(pdf_path, 'rb') as f:
            await query.message.reply_document(document=f, filename="AI_Response.pdf")
            
        os.remove(pdf_path)
        await sent_msg.delete()
    except Exception as e:
        await sent_msg.edit_text("❌ خطا در ساخت PDF.")
    return
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/bot.py
git commit -m "feat: add Convert to PDF button and callback handler"
```

### Task 5: Bot UI - TIPS System Logic

**Files:**
- Modify: `backend/app/bot.py`

- [ ] **Step 1: Detect Math and Send TIP**

In `backend/app/bot.py`, after sending the final AI response, add logic to check for math and send the tip:

```python
import asyncio
import re
from app.models import UserPreference
from sqlalchemy import select

# This should be inside the function where the final AI reply is sent.
# Ensure `db_session` and `user_id` (telegram user ID) are available.

async def _check_and_send_math_tip(context, chat_id, text, db_session, user_id):
    if not re.search(r'(\$|\\\[|\\begin\{)', text):
        return
        
    result = await db_session.execute(select(UserPreference).filter_by(telegram_user_id=user_id))
    pref = result.scalar_one_or_none()
    
    if pref and not pref.tip_pdf_math_dismissed:
        tip_kb = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("متوجه شدم", callback_data="tip_math_temp"),
                InlineKeyboardButton("دیگر نشان نده", callback_data="tip_math_perm")
            ]
        ])
        tip_msg = await context.bot.send_message(
            chat_id=chat_id,
            text="💡 نکته (TIPS): چون این پیام دارای فرمول ریاضی است، برای خوانایی بهتر می‌توانید با زدن دکمه «تبدیل به PDF» در پیام بالا، آن را به فایل تبدیل کنید.",
            reply_markup=tip_kb
        )
        
        # Schedule auto-delete
        async def delete_later():
            await asyncio.sleep(30)
            try:
                await context.bot.delete_message(chat_id=chat_id, message_id=tip_msg.message_id)
            except Exception:
                pass
        
        asyncio.create_task(delete_later())

# Call `await _check_and_send_math_tip(...)` right after the final AI message is sent.
```

- [ ] **Step 2: Handle TIPS Callbacks**

In `backend/app/bot.py` callback handler:

```python
if query.data in ["tip_math_temp", "tip_math_perm"]:
    await query.answer()
    try:
        await query.message.delete()
    except Exception:
        pass
        
    if query.data == "tip_math_perm":
        # Extract user_id from update
        u_id = update.effective_user.id
        # Assuming db session is `db`
        res = await db.execute(select(UserPreference).filter_by(telegram_user_id=u_id))
        user_pref = res.scalar_one_or_none()
        if user_pref:
            user_pref.tip_pdf_math_dismissed = True
            await db.commit()
    return
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/bot.py
git commit -m "feat: implement TIPS system for math PDF conversion"
```