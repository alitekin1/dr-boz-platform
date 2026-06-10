import os
import re
import subprocess
import tempfile
import uuid
import html as html_module

LATEX_BLOCK_PATTERN = re.compile(
    r'\[\s*(.+?)\s*\\\s*\]',
    re.DOTALL
)

LATEX_COMMANDS = [
    r'\\frac', r'\\dfrac', r'\\tfrac',
    r'\\int', r'\\iint', r'\\iiint', r'\\oint',
    r'\\sum', r'\\prod', r'\\bigcup', r'\\bigcap',
    r'\\lim', r'\\limsup', r'\\liminf',
    r'\\sqrt', r'\\nthroot',
    r'\\cdot', r'\\times', r'\\div',
    r'\\pm', r'\\mp', r'\\ast', r'\\circ',
    r'\\quad', r'\\qquad', r'\\,', r'\\;', r'\\!',
    r'\\boxed', r'\\text', r'\\mathrm', r'\\mathbf', r'\\mathit',
    r'\\alpha', r'\\beta', r'\\gamma', r'\\delta', r'\\epsilon',
    r'\\theta', r'\\lambda', r'\\mu', r'\\pi', r'\\sigma',
    r'\\phi', r'\\omega', r'\\Delta', r'\\Omega', r'\\Sigma',
    r'\\infty', r'\\partial', r'\\nabla',
    r'\\neq', r'\\approx', r'\\equiv', r'\\sim', r'\\propto',
    r'\\leq', r'\\geq', r'\\ll', r'\\gg',
    r'\\left', r'\\right', r'\\bigl', r'\\bigr',
    r'\\begin\{', r'\\end\{',
    r'\\displaystyle', r'\\limits',
    r'\\textbf', r'\\textit', r'\\underline',
    r'\\rightarrow', r'\\leftarrow', r'\\Rightarrow', r'\\Leftarrow',
    r'\\in', r'\\notin', r'\\subset', r'\\supset',
    r'\\cup', r'\\cap', r'\\setminus',
    r'\\forall', r'\\exists', r'\\neg', r'\\land', r'\\lor',
    r'\\angle', r'\\triangle', r'\\square',
    r'\\dots', r'\\cdots', r'\\vdots', r'\\ddots',
    r'\\hat', r'\\bar', r'\\tilde', r'\\vec', r'\\dot', r'\\ddot',
    r'\\degree',
]

LATEX_COMMAND_PATTERN = re.compile(
    r'(?<!\$)(?<!\\\$)(' + '|'.join(LATEX_COMMANDS) + r')(?!\$)(?!\\\$)',
    re.IGNORECASE
)

SECTION_TITLES = [
    r'^مثال\s*[:\n]',
    r'^صورت مسئله\s*[:\n]',
    r'^صورت سوال\s*[:\n]',
    r'^حل\s*[:\n]',
    r'^نتیجه\s*[:\n]',
    r'^نتیجه نهایی\s*[:\n]',
    r'^پاسخ\s*[:\n]',
    r'^پاسخ نهایی\s*[:\n]',
    r'^توضیح\s*[:\n]',
    r'^نکته\s*[:\n]',
    r'^مرحله\s*[:\n]',
    r'^گام\s*[:\n]',
    r'^بخش\s*[:\n]',
    r'^پس\s*[:\n]',
    r'^داده‌ها\s*[:\n]',
    r'^مراحل حل\s*[:\n]',
]

SECTION_TITLE_PATTERN = re.compile(
    r'^(' + '|'.join(SECTION_TITLES) + r')(.*)',
    re.MULTILINE
)

TIPS_PATTERNS = [
    r'اگر خواستی.*',
    r'برای تمرین بیشتر.*',
    r'نمونه سخت‌تر.*',
    r'نمونه سختتر.*',
    r'سوال دیگه.*',
    r'پرسش دیگری.*',
    r'علی جان.*',
    r'🐐.*',
    r'سیک حل کنم.*',
]

def _remove_tips(text: str) -> str:
    for pattern in TIPS_PATTERNS:
        text = re.sub(pattern, '', text, flags=re.IGNORECASE)
    return text.strip()

def _clean_markdown(text: str) -> str:
    text = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', text)
    text = re.sub(r'(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)', r'<em>\1</em>', text)
    text = re.sub(r'`(.+?)`', r'<code>\1</code>', text)
    text = re.sub(r'\\(?![a-zA-Z\[\]{}\(\)_%&$#^~])', '', text)
    text = re.sub(r'^#+\s*', '', text, flags=re.MULTILINE)
    text = re.sub(r'^[-*]\s+', '• ', text, flags=re.MULTILINE)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text

def _wrap_latex_in_delimiters(text: str) -> str:
    text = re.sub(r'(?<!\\)\bint\b', r'\\int', text)
    result = LATEX_BLOCK_PATTERN.sub(r'$$ \1 $$', text)
    
    lines = result.split('\n')
    processed_lines = []
    
    for line in lines:
        stripped = line.strip()
        
        if not stripped:
            processed_lines.append(line)
            continue
        
        if stripped.startswith('$$') or stripped.startswith('\\[') or stripped.startswith('$'):
            processed_lines.append(line)
            continue
        
        if stripped.startswith('• ') or stripped.startswith('- '):
            processed_lines.append(line)
            continue
        
        has_latex = LATEX_COMMAND_PATTERN.search(line)
        if has_latex and not any(c in stripped for c in ['$$', '\\[', '$', '<']):
            processed_lines.append(f'$$ {stripped} $$')
        else:
            processed_lines.append(line)
    
    return '\n'.join(processed_lines)

def _process_math_blocks(text: str) -> str:
    def replace_math_block(match):
        content = match.group(1).strip()
        return f'<div class="math-container">$$ {content} $$</div>'
    
    text = re.sub(r'\$\$\s*(.+?)\s*\$\$', replace_math_block, text, flags=re.DOTALL)
    return text

def _fix_rtl_ltr_mixing(text: str) -> str:
    text = re.sub(
        r'(\d+\.?\d*)\s*([a-zA-Z/³²°]+)',
        r'<span class="ltr">\1 \2</span>',
        text
    )
    return text

def _escape_html(text: str) -> str:
    return html_module.escape(text)

def _structure_sections(text: str) -> str:
    lines = text.split('\n')
    result = []
    current_section = None
    current_content = []
    
    def flush_section():
        nonlocal current_section, current_content
        if current_section is not None:
            content_html = '\n'.join(current_content).strip()
            if content_html:
                escaped_title = _escape_html(current_section)
                result.append('<div class="section">')
                result.append(f'<div class="section-title">{escaped_title}</div>')
                result.append('<div class="section-content">')
                result.append(content_html)
                result.append('</div>')
                result.append('</div>')
        current_section = None
        current_content = []
    
    for line in lines:
        stripped = line.strip()
        
        if not stripped:
            if current_section is not None:
                current_content.append('<br/>')
            continue
        
        match = SECTION_TITLE_PATTERN.match(stripped)
        if match:
            flush_section()
            title_match = match.group(1).rstrip(':').strip()
            title_rest = match.group(2).strip()
            if title_rest:
                current_section = f"{title_match}: {title_rest}"
            else:
                current_section = title_match
            current_content = []
        else:
            if current_section is None:
                current_section = 'پاسخ'
                current_content = []
            current_content.append(line)
    
    flush_section()
    
    return '\n'.join(result)

async def generate_pdf_from_markdown(markdown_text: str) -> str:
    """Generates a professional branded PDF and returns the path to the generated file."""
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    
    cleaned_text = _remove_tips(markdown_text)
    cleaned_text = _clean_markdown(cleaned_text)
    processed_text = _wrap_latex_in_delimiters(cleaned_text)
    processed_text = _process_math_blocks(processed_text)
    processed_text = _fix_rtl_ltr_mixing(processed_text)
    structured_html = _structure_sections(processed_text)
    
    with tempfile.NamedTemporaryFile(suffix=".html", delete=False, mode='w', encoding='utf-8') as html_file:
        html_file.write(structured_html)
        html_path = html_file.name

    output_path = os.path.join(tempfile.gettempdir(), f"export_{uuid.uuid4().hex}.pdf")
    
    try:
        process = subprocess.run(
            ["node", "gen_pdf.js", html_path, output_path],
            cwd=base_dir,
            capture_output=True,
            text=True,
            check=True
        )
    except subprocess.CalledProcessError as e:
        if os.path.exists(html_path):
            os.remove(html_path)
        raise RuntimeError(f"PDF Generation failed: {e.stderr}")
        
    os.remove(html_path)
    return output_path
