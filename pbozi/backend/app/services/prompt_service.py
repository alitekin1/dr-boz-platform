import os
import re
from html import escape
from datetime import datetime
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models import Skill, Tool

class PromptService:
    @staticmethod
    async def resolve_prompt(content: str, db: AsyncSession, *, allowed_skills: list[str] | None = None, allowed_tools: list[str] | None = None) -> str:
        if not content:
            return ""

        # Find all placeholders starting with @
        # We look for @ followed by characters that look like a variable name or a file path
        # We avoid picking up trailing punctuation like . or , if they aren't part of a file extension
        matches = re.finditer(r'@([a-zA-Z0-9_\-\.\/]+)', content)
        
        resolved_map = {}
        
        for match in matches:
            placeholder = match.group(1)
            # If it ends with punctuation that's likely not part of the name/path (e.g. at end of sentence)
            if placeholder.endswith('.') or placeholder.endswith(',') or placeholder.endswith('?'):
                # But only if it doesn't look like a file extension with at least one char after last dot
                # Actually, simpler: if it's one of our known keywords, trim it.
                if placeholder[:-1] in ["skills", "today", "tools"]:
                    placeholder = placeholder[:-1]
            
            full_placeholder = f"@{placeholder}"
            if full_placeholder in resolved_map:
                continue
            
            if placeholder == "today":
                resolved_map[full_placeholder] = datetime.now().strftime("%Y-%m-%d")
            elif placeholder == "skills":
                resolved_map[full_placeholder] = await PromptService._get_skills_text(db, allowed_skills=allowed_skills)
            elif placeholder == "tools":
                resolved_map[full_placeholder] = await PromptService._get_tools_text(db, allowed_tools=allowed_tools)
            else:
                # Try to resolve as a file path
                file_content = await PromptService._read_file_safe(placeholder)
                if file_content is not None:
                    resolved_map[full_placeholder] = file_content
                else:
                    # Keep it as is if not found
                    pass

        # Replace placeholders
        for p, val in resolved_map.items():
            content = content.replace(p, val)
            
        return content

    @staticmethod
    async def _read_file_safe(path: str) -> str | None:
        # Check current dir, and also one level up if in backend/
        paths_to_try = [path]
        if os.path.basename(os.getcwd()) == "backend":
            paths_to_try.append(os.path.join("..", path))
        
        for p in paths_to_try:
            if os.path.isfile(p):
                try:
                    with open(p, 'r', encoding='utf-8') as f:
                        return f.read()
                except Exception as e:
                    return f"[Error reading file {p}: {str(e)}]"
        return None

    @staticmethod
    async def _get_skills_text(db: AsyncSession, *, allowed_skills: list[str] | None = None) -> str:
        query = select(Skill).where(Skill.is_active == True)
        if allowed_skills is not None:
            if not allowed_skills:
                return "No active skills available."
            query = query.where(Skill.name.in_(allowed_skills))
        result = await db.execute(query)
        skills = result.scalars().all()
        if not skills:
            return "No active skills available."
        
        xml_parts = ["<skills>"]
        for s in skills:
            xml_parts.append("  <skill>")
            xml_parts.append(f"    <name>{escape(s.name or '')}</name>")
            if s.description:
                xml_parts.append(f"    <description>{escape(s.description)}</description>")
            if s.when_to_use:
                xml_parts.append(f"    <when_to_use>{escape(s.when_to_use)}</when_to_use>")
            if s.avoid_when:
                xml_parts.append(f"    <avoid_when>{escape(s.avoid_when)}</avoid_when>")
            if s.file_path:
                xml_parts.append(f"    <path>{escape(s.file_path)}</path>")
                xml_parts.append(f"    <skill_file>{escape(os.path.join(s.file_path, 'SKILL.md'))}</skill_file>")
                xml_parts.append("    <read_instructions>Use the read_skill tool with this exact skill name to read SKILL.md and file list. Use read_skill_file with a relative path from the skill directory to read supporting files.</read_instructions>")
            xml_parts.append("  </skill>")
        xml_parts.append("</skills>")
        return "\n".join(xml_parts)

    @staticmethod
    async def _get_tools_text(db: AsyncSession, *, allowed_tools: list[str] | None = None) -> str:
        query = select(Tool).where(Tool.is_active == True)
        if allowed_tools is not None:
            if not allowed_tools:
                return "No active tools available."
            query = query.where(Tool.name.in_(allowed_tools))
        result = await db.execute(query)
        tools = result.scalars().all()
        if not tools:
            return "No active tools available."
        
        lines = []
        for t in tools:
            lines.append(f"- {t.name}: {t.description}")
        return "\n".join(lines)
