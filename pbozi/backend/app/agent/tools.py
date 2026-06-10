import os
import subprocess
import tempfile
import json
import asyncio
from typing import Type, Any
from pydantic import BaseModel, Field
from langchain_core.tools import tool
from langchain_community.tools import DuckDuckGoSearchRun
from app.database import async_session

# DuckDuckGo search tool
ddg_search = DuckDuckGoSearchRun()

class WebSearchInput(BaseModel):
    query: str = Field(description="The precise search query to look up. Example: 'Apple and NVIDIA revenue 2025 comparison'")

@tool("web_search", args_schema=WebSearchInput)
def web_search(query: str) -> str:
    """Search the web for real-time information, financial data, news, and complex reports. 
    Use this tool when you need facts or data that you don't already have in your knowledge base.
    """
    try:
        result = ddg_search.run(query)
        if not result or not result.strip():
            return f"No search results found for: {query}. Try a different query."
        return result
    except Exception as e:
        return f"Search error: {str(e)}. Tip: Try a shorter or more general query."

class PythonRunInput(BaseModel):
    code: str = Field(description="The complete, valid Python code to run. Use print() to output results.")
    send_to_chat: bool = Field(
        default=False,
        description=(
            "Set true only when the user explicitly wants the generated files sent directly in chat. "
            "Leave false for intermediate charts/files that will be embedded into a PDF or used in later steps."
        ),
    )

@tool("run_python", args_schema=PythonRunInput)
def run_python(code: str, send_to_chat: bool = False) -> str:
    """Run Python code for data science, analysis, or chart generation.
    Environment includes: pandas, matplotlib, requests, sqlalchemy.
    Save charts or files with explicit filenames so later steps can use them.
    For PDF workflows, keep send_to_chat=false for intermediate chart/image files and embed them into the PDF.
    Final PDF files created by this tool are delivered to chat automatically.
    Set send_to_chat=true only when the user explicitly wants the generated files sent directly in chat.
    """
    from app.services.tool_file_tracking import (
        changed_tool_files,
        existing_tool_files_from_output,
        snapshot_tool_files,
    )
    
    cwd = os.getcwd()
    temp_dir = tempfile.gettempdir()
    import time
    start_time = time.time()
    before_files = snapshot_tool_files(cwd, extra_dirs=[temp_dir])
    
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write(code)
        temp_path = f.name

    try:
        result = subprocess.run(
            ["python", temp_path],
            timeout=60,
            capture_output=True,
            text=True,
            cwd=cwd
        )
        output = result.stdout
        if result.stderr:
            output += "\n--- ERRORS ---\n" + result.stderr
            
        # Detect new or modified files in the working directory and common temp output dir.
        new_files = changed_tool_files(
            before_files,
            cwd,
            extra_dirs=[temp_dir],
            exclude_paths={temp_path},
        )
        output_paths = existing_tool_files_from_output(output, cwd, start_time=start_time)
        if output_paths:
            new_files = sorted(set(new_files) | set(output_paths))
        
        if new_files:
            res_data = {
                "output": output if output else "Code executed successfully.",
                "new_files": [os.path.abspath(img) for img in new_files],
                "send_to_chat": send_to_chat,
            }
            return json.dumps(res_data, ensure_ascii=False)
            
        return output if output else "Code executed successfully (no output)."
    except subprocess.TimeoutExpired:
        return "Error: Timeout (60s). Optimize your code or use a smaller dataset."
    except Exception as e:
        return f"Python Runtime Error: {str(e)}"
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)

class PdfGeneratorInput(BaseModel):
    content: str = Field(description="The content of the report. You can use Markdown or LaTeX depending on the mode.")
    output_filename: str = Field(description="The output filename ending in .pdf. Example: 'Annual_Report_2026.pdf'")
    latex_mode: str = Field(default="body", description="Either 'body' (takes markdown) or 'full_document' (takes complete LaTeX).")
    rtl: bool = Field(default=True, description="Whether to enable RTL/Persian support.")
    title: str | None = Field(default=None, description="Optional title for the document.")

@tool("pdf_generator", args_schema=PdfGeneratorInput)
async def pdf_generator(content: str, output_filename: str, latex_mode: str = "body", rtl: bool = True, title: str | None = None) -> str:
    """Generate a professional downloadable PDF document from text or LaTeX.
    Use this as the final step to deliver a professional report to the user.
    """
    from app.llm import run_pdf_generator_tool
    args = {
        "content": content,
        "output_filename": output_filename,
        "latex_mode": latex_mode,
        "rtl": rtl,
        "title": title
    }
    try:
        result = await run_pdf_generator_tool(args)
        return json.dumps(result, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False)

class ImageGeneratorInput(BaseModel):
    prompt: str = Field(description="The highly detailed prompt for image generation.")

@tool("image_generator", args_schema=ImageGeneratorInput)
async def image_generator(prompt: str, config: dict | None = None) -> str:
    """Generate a high-quality image using AI. Use this for creative requests or visual illustrations.
    NOT for charts or data plots (use run_python for those).
    """
    from app.llm import run_image_generator_tool
    # We need a chat_id but LangChain tools don't receive it by default.
    # In this app, we can try to extract it from context or just pass None for now.
    # Actually, for billing, it's better if we have it.
    async with async_session() as db:
        try:
            result = await run_image_generator_tool(db, None, {"prompt": prompt})
            return json.dumps(result, ensure_ascii=False)
        except Exception as e:
            return json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False)

class ReadSkillInput(BaseModel):
    skill_name: str = Field(description="The exact name of the skill to read instructions for.")

class ReadSkillFileInput(BaseModel):
    skill_name: str = Field(description="The exact name of the skill.")
    relative_path: str = Field(description="A file path relative to the skill directory, for example references/usage.md.")

class SearchProjectInput(BaseModel):
    query: str = Field(description="The search query to find relevant information within the project's documents and knowledge base.")
    n_results: int = Field(default=5, description="The number of relevant chunks to retrieve. Default is 5.")

@tool("read_skill", args_schema=ReadSkillInput)
async def read_skill(skill_name: str) -> str:
    """Read the detailed instructions and files for a specific Skill.
    Use this tool when you determine a Skill is relevant to the user's request.
    """
    from sqlalchemy import select
    from app.admin_skills_routes import list_skill_files
    from app.models import Skill
    
    async with async_session() as db:
        result = await db.execute(select(Skill).where(Skill.name == skill_name, Skill.is_active == True))
        skill = result.scalars().first()
        if not skill:
            return f"Skill '{skill_name}' not found or is disabled."

        files = list_skill_files(skill.file_path)
        file_list = "\n".join(f"- {path}" for path in files) if files else "No supporting files found."
        return (
            f"Skill Name: {skill.name}\n"
            f"Skill Directory: {skill.file_path or 'not available'}\n"
            f"Files:\n{file_list}\n\n"
            f"Instructions:\n{skill.instructions}"
        )

@tool("read_skill_file", args_schema=ReadSkillFileInput)
async def read_skill_file(skill_name: str, relative_path: str) -> str:
    """Read a supporting file from a Skill directory using a safe relative path."""
    from pathlib import Path
    from sqlalchemy import select
    from app.models import Skill

    async with async_session() as db:
        result = await db.execute(select(Skill).where(Skill.name == skill_name, Skill.is_active == True))
        skill = result.scalars().first()
        if not skill or not skill.file_path:
            return f"Skill '{skill_name}' not found, disabled, or has no directory."

        root = Path(skill.file_path).resolve()
        requested = (root / relative_path).resolve()
        if root not in requested.parents or not requested.is_file():
            return "File not found or path is outside the skill directory."

        if requested.stat().st_size > 200_000:
            return "File is too large to read through this tool."

        try:
            return requested.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            return "File is not UTF-8 text and cannot be read through this tool."
        except Exception as exc:
            return f"Error reading skill file: {exc}"

class SendFileInput(BaseModel):
    file_path: str = Field(description="The absolute or relative path to the file to upload to the user.")

@tool("send_file", args_schema=SendFileInput)
def send_file(file_path: str) -> str:
    """Send a file from the server to the user.
    Use this tool to upload a generated or existing file to the user's chat.
    Provide the path to the file.
    """
    import os
    import json
    
    if not os.path.isfile(file_path):
        return json.dumps({"ok": False, "error": f"File not found: {file_path}"})
    
    res_data = {
        "ok": True,
        "storage_path": file_path,
        "message": f"File {file_path} is ready to be sent."
    }
    return json.dumps(res_data, ensure_ascii=False)


class ChartGeneratorInput(BaseModel):
    chart_type: str = Field(
        description="Type of chart: 'bar', 'line', 'pie', 'scatter', 'histogram'"
    )
    title: str = Field(description="Title of the chart")
    labels: list[str] = Field(
        default=[],
        description="Labels for x-axis or pie slices (e.g. ['Jan', 'Feb', 'Mar'])"
    )
    values: list[float] = Field(
        description="Numeric values for the chart data points"
    )
    x_label: str = Field(default="", description="X-axis label")
    y_label: str = Field(default="", description="Y-axis label")
    filename: str = Field(
        default="chart.png",
        description="Output filename (must end with .png)"
    )
    colors: list[str] = Field(
        default=[],
        description="Optional list of color names or hex codes for bars/slices"
    )

@tool("chart_generator", args_schema=ChartGeneratorInput)
def chart_generator(
    chart_type: str,
    title: str,
    values: list[float],
    labels: list[str] | None = None,
    x_label: str = "",
    y_label: str = "",
    filename: str = "chart.png",
    colors: list[str] | None = None,
) -> str:
    """Generate a chart/graph (bar, line, pie, scatter, histogram) and save it as a PNG image.
    Use this for data visualization requests. The chart is saved and can be sent to the user.
    """
    import os
    import json
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    if labels is None:
        labels = []
    if colors is None:
        colors = []

    if not filename.lower().endswith(".png"):
        filename += ".png"

    output_dir = os.path.join(os.getcwd(), "uploads", "charts")
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, filename)

    try:
        fig, ax = plt.subplots(figsize=(10, 6))

        if chart_type == "bar":
            x = range(len(values))
            ax.bar(x, values, color=colors if colors else None)
            if labels:
                ax.set_xticks(list(x))
                ax.set_xticklabels(labels, rotation=45, ha="right")
        elif chart_type == "line":
            ax.plot(values, marker="o", color=colors[0] if colors else None)
            if labels:
                ax.set_xticks(range(len(labels)))
                ax.set_xticklabels(labels, rotation=45, ha="right")
        elif chart_type == "pie":
            ax.pie(
                values,
                labels=labels if labels else None,
                colors=colors if colors else None,
                autopct="%1.1f%%",
                startangle=90,
            )
        elif chart_type == "scatter":
            x_vals = list(range(len(values)))
            ax.scatter(x_vals, values, color=colors[0] if colors else "blue")
            if labels:
                ax.set_xticks(x_vals)
                ax.set_xticklabels(labels, rotation=45, ha="right")
        elif chart_type == "histogram":
            ax.hist(values, bins="auto", color=colors[0] if colors else "blue", edgecolor="black")
        else:
            return json.dumps({"ok": False, "error": f"Unsupported chart type: {chart_type}"}, ensure_ascii=False)

        ax.set_title(title, fontsize=14, fontweight="bold")
        if x_label and chart_type != "pie":
            ax.set_xlabel(x_label)
        if y_label and chart_type != "pie":
            ax.set_ylabel(y_label)

        plt.tight_layout()
        plt.savefig(output_path, dpi=150)
        plt.close(fig)

        return json.dumps({
            "ok": True,
            "file_path": output_path,
            "filename": filename,
            "chart_type": chart_type,
            "message": f"Chart saved as {filename}",
        }, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False)


tools_list = [web_search, run_python, pdf_generator, image_generator, read_skill, read_skill_file, send_file, chart_generator]
