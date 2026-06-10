const puppeteer = require('puppeteer');
const fs = require('fs');
const path = require('path');

const inputPath = process.argv[2];
const outputPath = process.argv[3];

if (!inputPath || !outputPath) {
    console.error("Usage: node gen_pdf.js <input.html> <output.pdf>");
    process.exit(1);
}

const htmlContent = fs.readFileSync(inputPath, 'utf8');

const assetsDir = path.join(__dirname, 'app', 'assets', 'images');
const mascotPath = path.join(assetsDir, 'mascot.png');
const mascotBase64 = fs.readFileSync(mascotPath, 'base64');

const fontsDir = path.join(__dirname, 'app', 'assets', 'fonts');
const vazirFontPath = path.join(fontsDir, 'Vazirmatn-Regular.ttf');
const vazirFontBase64 = fs.readFileSync(vazirFontPath, 'base64');

const fontStyle = `
<style>
@font-face {
    font-family: 'Vazirmatn';
    src: url(data:font/ttf;base64,${vazirFontBase64}) format('truetype');
    font-weight: normal;
    font-style: normal;
}
</style>
`;

const headerHTML = `
${fontStyle}
<div style="display: flex; align-items: center; justify-content: flex-start; gap: 12px; width: 100%; padding: 8px 16mm; border-bottom: 1.5px solid #07142D; direction: rtl; font-family: 'Vazirmatn', Tahoma, sans-serif;">
    <img src="data:image/png;base64,${mascotBase64}" style="width: 28px; height: 28px; border-radius: 50%;" alt="" />
    <span style="font-size: 16px; font-weight: 800; color: #07142D;">دکتر بز</span>
</div>
`;

const footerHTML = `
${fontStyle}
<div style="display: flex; align-items: center; justify-content: space-between; width: 100%; padding: 8px 16mm 12px 16mm; border-top: 1px solid #E5E7EB; font-family: 'Vazirmatn', Tahoma, sans-serif; font-size: 10px; color: #6B7280; direction: rtl;">
    <span style="direction: ltr; unicode-bidi: embed; font-family: monospace;">@drbozai_bot</span>
    <span>صفحه <span class="pageNumber" style="font-weight: 700; color: #07142D;"></span></span>
</div>
`;

const pageHTML = `
<!DOCTYPE html>
<html dir="rtl" lang="fa">
<head>
    <meta charset="UTF-8">
    <script>
    window.MathJax = {
        tex: {
            inlineMath: [['$', '$'], ['\\\\(', '\\\\)']],
            displayMath: [['$$', '$$'], ['\\\\[', '\\\\]']],
            processEscapes: true,
            processEnvironments: true,
            tags: 'none'
        },
        options: {
            skipHtmlTags: ['script', 'noscript', 'style', 'textarea', 'pre', 'code'],
            ignoreHtmlClass: 'tex2jax_ignore'
        },
        startup: {
            ready: () => {
                MathJax.startup.defaultReady();
                MathJax.startup.promise.then(() => {
                    window._mathjaxReady = true;
                });
            }
        }
    };
    </script>
    <script src="https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-mml-chtml.js" async></script>
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Vazirmatn:wght@100;200;300;400;500;600;700;800;900&display=swap');
        
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        
        @page {
            size: A4 portrait;
            margin: 18mm 16mm 22mm 16mm;
        }
        
        html, body {
            width: 100%;
            font-family: 'Vazirmatn', Tahoma, Arial, sans-serif;
            background: #ffffff;
            color: #1a1a1a;
            font-size: 11pt;
            line-height: 1.85;
            direction: rtl;
            text-align: right;
            -webkit-print-color-adjust: exact;
            print-color-adjust: exact;
        }
        
        .content-wrapper {
            width: 100%;
            direction: rtl;
            text-align: right;
        }
        
        .section {
            margin-bottom: 16px;
            padding-bottom: 12px;
            border-bottom: 1px solid #E5E7EB;
            direction: rtl;
            text-align: right;
        }
        
        .section:last-child {
            border-bottom: none;
            margin-bottom: 0;
        }
        
        .section-title {
            font-family: 'Vazirmatn', Tahoma, sans-serif;
            font-size: 12pt;
            font-weight: 700;
            color: #07142D;
            margin-bottom: 8px;
            display: flex;
            align-items: center;
            gap: 8px;
            direction: rtl;
        }
        
        .section-title::before {
            content: '';
            display: inline-block;
            width: 3px;
            height: 18px;
            background: #2563EB;
            border-radius: 2px;
            flex-shrink: 0;
        }
        
        .section-content {
            font-family: 'Vazirmatn', Tahoma, sans-serif;
            font-size: 11pt;
            color: #1a1a1a;
            line-height: 2;
            direction: rtl;
            text-align: right;
        }
        
        .section-content br {
            display: block;
            content: "";
            margin-top: 4px;
        }
        
        .math-container {
            margin: 12px auto;
            padding: 12px 16px;
            background: #F9FAFB;
            border-radius: 8px;
            border: 1px solid #E5E7EB;
            direction: ltr;
            text-align: center;
            display: block;
            width: 100%;
        }
        
        .math-container .mjx-chtml {
            display: inline-block !important;
            text-align: center !important;
            font-size: 110% !important;
        }
        
        .section-content strong, .section-content b {
            color: #07142D;
            font-weight: 700;
        }
        
        .section-content em, .section-content i {
            font-style: italic;
        }
        
        .section-content code {
            font-family: 'Courier New', Courier, monospace;
            direction: ltr;
            unicode-bidi: embed;
            font-size: 10pt;
            background: #F3F4F6;
            padding: 1px 4px;
            border-radius: 3px;
        }
        
        .ltr {
            direction: ltr;
            unicode-bidi: isolate;
            display: inline-block;
        }
        
        pre {
            background-color: #F9FAFB;
            padding: 10px 14px;
            border-radius: 6px;
            border: 1px solid #E5E7EB;
            direction: ltr;
            text-align: left;
            overflow-x: auto;
            font-size: 10pt;
            margin: 10px 0;
        }
        
        pre code {
            background: none;
            padding: 0;
        }
    </style>
</head>
<body>
    <div class="content-wrapper">
        ${htmlContent}
    </div>
</body>
</html>
`;

(async () => {
    const browser = await puppeteer.launch({ 
        args: [
            '--no-sandbox', 
            '--disable-setuid-sandbox',
            '--disable-dev-shm-usage',
            '--disable-gpu'
        ],
        headless: 'new'
    });
    const page = await browser.newPage();
    
    await page.setContent(pageHTML, { 
        waitUntil: 'networkidle0',
        timeout: 30000 
    });
    
    try {
        await page.waitForFunction(
            () => window._mathjaxReady === true, 
            { timeout: 25000 }
        );
        await new Promise(resolve => setTimeout(resolve, 2000));
    } catch (e) {
        console.warn('MathJax timeout, proceeding anyway');
    }
    
    await page.pdf({ 
        path: outputPath, 
        format: 'A4', 
        printBackground: true,
        margin: { 
            top: '18mm', 
            right: '16mm', 
            bottom: '22mm', 
            left: '16mm' 
        },
        displayHeaderFooter: true,
        headerTemplate: headerHTML,
        footerTemplate: footerHTML,
        preferCSSPageSize: true
    });
    await browser.close();
    console.log('PDF generated successfully');
})();
