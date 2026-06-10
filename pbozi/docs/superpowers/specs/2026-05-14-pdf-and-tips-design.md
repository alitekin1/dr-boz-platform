# PDF Export & TIPS System Design

## 1. Overview
The goal is to allow users to easily convert AI responses into beautifully formatted PDFs, especially when they contain math formulas or complex formatting. We will also introduce a "TIPS" system to gently educate users about this and other features.

## 2. Components

### 2.1 PDF Generation Service (Node.js/Puppeteer)
- **Tech Stack**: `puppeteer`, `markdown-it`, `markdown-it-mathjax3`, CSS with `Vazirmatn` font.
- **Workflow**:
  - Python backend sends Markdown content to a small JS script.
  - The script wraps the Markdown in an HTML template.
  - `markdown-it` converts it to HTML, rendering math formulas correctly.
  - A script dynamically sets direction to `rtl` for Persian/Arabic texts and `ltr` for English, while preserving proper BiDi (Bidirectional) text rendering.
  - Puppeteer loads the HTML, waits for rendering, and exports a PDF file.

### 2.2 Bot UI Updates (Python/Telegram Bot)
- Add an inline keyboard button `📄 تبدیل به PDF` to the last generated message of an AI response.
- When clicked, the bot displays a "⏳" status, calls the PDF generation service, and replies with the generated PDF document.

### 2.3 TIPS Feature System
- **Purpose**: Show temporary educational tooltips to users.
- **Trigger**: When an AI response contains math formatting (e.g., `$`, `\[`, `\begin{`), the bot evaluates if the user needs a tip.
- **Database**: 
  - Add a new table or user preference column (e.g., `user_tips_preferences`) to track which tips a user has permanently dismissed (e.g., `tip_pdf_math_dismissed = True`).
- **Flow**:
  1. AI sends response. Bot detects math.
  2. Bot checks DB. If `tip_pdf_math_dismissed` is False, bot sends a tip message:
     *"💡 نکته (TIPS): چون این پیام دارای فرمول ریاضی است، برای خوانایی بهتر می‌توانید با زدن دکمه «تبدیل به PDF» در پیام بالا، آن را به فایل تبدیل کنید."*
  3. The tip has two buttons:
     - `متوجه شدم` -> Deletes the tip message immediately.
     - `دیگر نشان نده` -> Deletes the tip message AND updates DB to never show this tip again.
  4. An asynchronous task (`asyncio.sleep(30)`) is spawned. If 30 seconds pass without user interaction, the tip message is automatically deleted to keep the chat clean.

## 3. GEMINI.md Update
- The concept of the "TIPS" feature will be formalized in the project's `GEMINI.md` file so future AI agents know what "TIPS" refers to and can implement new ones following the same pattern (temporary message, 2 buttons, auto-delete).