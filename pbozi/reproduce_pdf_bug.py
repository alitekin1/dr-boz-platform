import asyncio
import os
import sys
import json

# Add current directory to path to import app
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "backend")))

from backend.app.llm import run_pdf_generator_tool

async def main():
    print("Testing PDF generation with special characters and Persian text...")
    content = "این یک گزارش تست است.\n\nدرصد سود: 50%\n\nنام شرکت: A & B\n\n**متن ضخیم**"
    args = {
        "content": content,
        "output_filename": "test_reproduce.pdf",
        "latex_mode": "body",
        "rtl": True,
        "title": "گزارش تست"
    }
    
    try:
        result = await run_pdf_generator_tool(args)
        print(f"Result: {json.dumps(result, indent=2, ensure_ascii=False)}")
        if result.get("ok"):
            print(f"PDF generated: {result.get('file_name')}")
            print(f"Engine used: {result.get('engine')}")
            if result.get("warning"):
                print(f"Warning: {result.get('warning')}")
        else:
            print(f"Error: {result.get('error')}")
    except Exception as e:
        print(f"Exception: {e}")

if __name__ == "__main__":
    asyncio.run(main())
