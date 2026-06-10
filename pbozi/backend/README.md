# JGPTi Backend

## Setup
```bash
source venv/bin/activate
uvicorn app.main:app --reload --port 8000
```

## PDF Generator Tool Runtime
Builtin tool `pdf_generator` compiles PDFs with XeLaTeX (RTL + Vazirmatn + LaTeX math).

Required system dependencies:
```bash
sudo apt-get update
sudo apt-get install -y texlive-xetex texlive-lang-arabic texlive-fonts-recommended
```

## Admin
ادمین میتونه پروایدر OpenAI-compatible اضافه کنه + مدل + قیمت

## Telegram Bot
Token: configured in .env
