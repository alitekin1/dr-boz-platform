# Design Spec: PDF Layout and Font Fixes (RTL Branding)

Date: 2026-05-16
Topic: PDF Export Improvements
Status: Approved (Design)

## Context
The current PDF export for "Dr. Bose" (دکتر بز) has several layout and branding issues:
1. The logo and title are placed on the left side of the header, which is incorrect for a Persian (RTL) document.
2. The "Vazirmatn" font is not correctly applied to the header and footer because the font import is missing in the Puppeteer templates.
3. The header and footer content are too close to the edges of the paper, lacking horizontal padding that matches the main content margins.

## Goals
- Align the logo and title to the right side of the header (standard RTL branding).
- Ensure "Vazirmatn" font is rendered correctly in both the header and footer.
- Add horizontal padding (16mm) to the header and footer to align with the body content margins.
- Improve spacing and visual hierarchy in the header and footer.

## Proposed Changes

### 1. `backend/gen_pdf.js`
Modify the `headerHTML` and `footerHTML` templates to:
- **Import Vazirmatn:** Add the `@import` for Google Fonts inside the template `style` tags.
- **Correct Alignment:** 
    - Change `justify-content: flex-end` to `justify-content: flex-start` in the header (since `direction: rtl` is set, `flex-start` is the right side).
    - Swap the order of the logo and the text so the logo appears to the right of "دکتر بز".
- **Add Padding:** Add `padding: 8px 16mm` to both header and footer containers to match the `@page` margin of `16mm`.
- **Adjust Sizing:** Slightly increase logo size (to `28px`) and font size (to `16px`) for better visibility.

#### Header Template Update:
```html
<div style="display: flex; align-items: center; justify-content: flex-start; gap: 12px; width: 100%; padding: 8px 16mm; border-bottom: 1.5px solid #07142D; direction: rtl; font-family: 'Vazirmatn', Tahoma, sans-serif;">
    <style>@import url('https://fonts.googleapis.com/css2?family=Vazirmatn:wght@800&display=swap');</style>
    <img src="data:image/png;base64,${mascotBase64}" style="width: 28px; height: 28px; border-radius: 50%;" alt="" />
    <span style="font-size: 16px; font-weight: 800; color: #07142D;">دکتر بز</span>
</div>
```

#### Footer Template Update:
```html
<div style="display: flex; align-items: center; justify-content: space-between; width: 100%; padding: 8px 16mm 12px 16mm; border-top: 1px solid #E5E7EB; font-family: 'Vazirmatn', Tahoma, sans-serif; font-size: 10px; color: #6B7280; direction: rtl;">
    <style>@import url('https://fonts.googleapis.com/css2?family=Vazirmatn:wght@400;700&display=swap');</style>
    <span style="direction: ltr; unicode-bidi: embed; font-family: monospace;">@drbozai_bot</span>
    <span>صفحه <span class="pageNumber" style="font-weight: 700; color: #07142D;"></span></span>
</div>
```

## Verification Plan
1. **Manual Inspection:** Generate a PDF answer and verify:
    - Logo and "دکتر بز" are on the top-right.
    - Font matches the body text (Vazirmatn).
    - Footer is not touching the bottom edge and aligns horizontally with the content.
2. **Visual Check:** Compare with the provided `AI_Response.jpg` to ensure all reported problems are resolved.
