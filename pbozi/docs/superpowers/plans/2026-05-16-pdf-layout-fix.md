# PDF Layout and Font Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix branding, alignment, and typography in the PDF export to match RTL standards and user requirements.

**Architecture:** Modify the Puppeteer HTML templates in `backend/gen_pdf.js` to include font imports, correct flex-box direction, and add safe-area padding.

**Tech Stack:** Node.js, Puppeteer, CSS (Flexbox, @import)

---

### Task 1: Update Header and Footer Templates in `backend/gen_pdf.js`

**Files:**
- Modify: `backend/gen_pdf.js`

- [ ] **Step 1: Apply Font Import and RTL Alignment to `headerHTML`**

Replace the existing `headerHTML` constant with the updated version.

```javascript
const headerHTML = `
<div style="display: flex; align-items: center; justify-content: flex-start; gap: 12px; width: 100%; padding: 8px 16mm; border-bottom: 1.5px solid #07142D; direction: rtl; font-family: 'Vazirmatn', Tahoma, sans-serif;">
    <style>@import url('https://fonts.googleapis.com/css2?family=Vazirmatn:wght@800&display=swap');</style>
    <img src="data:image/png;base64,${mascotBase64}" style="width: 28px; height: 28px; border-radius: 50%;" alt="" />
    <span style="font-size: 16px; font-weight: 800; color: #07142D;">دکتر بز</span>
</div>
`;
```

- [ ] **Step 2: Apply Font Import and RTL Alignment to `footerHTML`**

Replace the existing `footerHTML` constant with the updated version.

```javascript
const footerHTML = `
<div style="display: flex; align-items: center; justify-content: space-between; width: 100%; padding: 8px 16mm 12px 16mm; border-top: 1px solid #E5E7EB; font-family: 'Vazirmatn', Tahoma, sans-serif; font-size: 10px; color: #6B7280; direction: rtl;">
    <style>@import url('https://fonts.googleapis.com/css2?family=Vazirmatn:wght@400;700&display=swap');</style>
    <span style="direction: ltr; unicode-bidi: embed; font-family: monospace;">@drbozai_bot</span>
    <span>صفحه <span class="pageNumber" style="font-weight: 700; color: #07142D;"></span></span>
</div>
`;
```

- [ ] **Step 3: Update @page margins in `pageHTML` (Optional Safety)**

Ensure the `@page` margin in the CSS matches the horizontal padding for a unified look. (The current script already uses `16mm` which matches our plan).

- [ ] **Step 4: Commit Changes**

```bash
git add backend/gen_pdf.js
git commit -m "fix(pdf): fix header/footer alignment, font loading, and margins for RTL"
```

---

### Task 2: Verification

- [ ] **Step 1: Check Backend Status**

Ensure the backend is running.
Run: `cd backend && source venv/bin/activate && uvicorn app.main:app --host 0.0.0.0 --port 7000 --reload`

- [ ] **Step 2: Trigger PDF Generation**

Use the UI or a test script to generate a PDF. 
If no test script exists, create a temporary `test_gen.py` to trigger the generation logic.

- [ ] **Step 3: Visual Inspection**

Verify the output PDF:
1. Logo and "دکتر بز" are on the top-right.
2. Font is Vazirmatn.
3. Margins are consistent (16mm from edges).
