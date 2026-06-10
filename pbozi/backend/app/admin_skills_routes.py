import os
import re
import shutil
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import List

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import get_session, async_session
from app.models import Skill
from app.schemas import SkillOut, SkillUpdate
from app.admin_routes import verify_admin
from app.services.admin_audit import create_admin_action
from app.services.codex_skill_sync import sync_all_codex_accounts

router = APIRouter(tags=["admin-skills"])

UPLOAD_DIR = Path("uploads/skills")
SKILL_DIR_SAFE_RE = re.compile(r"[^A-Za-z0-9._-]+")


@dataclass
class PreparedSkillBundle:
    name: str
    description: str
    usage_rules: str
    when_to_use: str
    avoid_when: str
    instructions: str
    skill_dir: Path


def _safe_skill_dir_name(name: str) -> str:
    safe_name = SKILL_DIR_SAFE_RE.sub("_", name.strip()).strip("._-")
    return safe_name or "skill"


def _unique_skill_dir(upload_dir: Path, folder_name: str) -> Path:
    skill_dir = upload_dir / folder_name
    counter = 1
    while skill_dir.exists():
        skill_dir = upload_dir / f"{folder_name}_{counter}"
        counter += 1
    return skill_dir


def _safe_extract_zip(zip_ref: zipfile.ZipFile, destination: Path) -> None:
    destination = destination.resolve()
    for member in zip_ref.infolist():
        member_path = Path(member.filename)
        if member_path.is_absolute() or ".." in member_path.parts:
            continue

        target_path = (destination / member_path).resolve()
        if destination not in target_path.parents and target_path != destination:
            continue

        if member.is_dir():
            target_path.mkdir(parents=True, exist_ok=True)
            continue

        target_path.parent.mkdir(parents=True, exist_ok=True)
        with zip_ref.open(member) as source, open(target_path, "wb") as target:
            shutil.copyfileobj(source, target)


def _find_skill_markdown(extracted_dir: Path) -> Path | None:
    matches = sorted(
        (path for path in extracted_dir.rglob("*") if path.is_file() and path.name.lower() == "skill.md"),
        key=lambda p: len(p.relative_to(extracted_dir).parts),
    )
    return matches[0] if matches else None


def _copy_skill_contents(source_dir: Path, target_dir: Path) -> None:
    target_dir.mkdir(parents=True, exist_ok=True)
    for item in source_dir.iterdir():
        target = target_dir / item.name
        if item.is_dir():
            shutil.copytree(item, target)
        else:
            shutil.copy2(item, target)


def list_skill_files(file_path: str | None) -> list[str]:
    if not file_path:
        return []
    root = Path(file_path)
    if not root.is_dir():
        return []
    files = []
    for path in root.rglob("*"):
        if path.is_file():
            files.append(path.relative_to(root).as_posix())
    return sorted(files)


def serialize_skill(skill: Skill) -> dict:
    return {
        "id": skill.id,
        "name": skill.name,
        "description": skill.description,
        "usage_rules": skill.usage_rules,
        "when_to_use": skill.when_to_use,
        "avoid_when": skill.avoid_when,
        "instructions": skill.instructions,
        "file_path": skill.file_path,
        "files": list_skill_files(skill.file_path),
        "is_active": skill.is_active,
        "created_at": skill.created_at,
        "updated_at": skill.updated_at,
    }


def prepare_skill_bundle(zip_path: Path, upload_dir: Path = UPLOAD_DIR) -> PreparedSkillBundle:
    upload_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".extract_", dir=upload_dir) as staging_name:
        staging_dir = Path(staging_name)
        with zipfile.ZipFile(zip_path, "r") as zip_ref:
            _safe_extract_zip(zip_ref, staging_dir)

        skill_md_path = _find_skill_markdown(staging_dir)
        if not skill_md_path:
            raise HTTPException(status_code=400, detail="SKILL.md not found in the zip file")

        try:
            skill_md_content = skill_md_path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            raise HTTPException(status_code=400, detail="SKILL.md must be UTF-8 encoded")

        name, description, usage_rules, when_to_use, avoid_when = parse_skill_markdown(skill_md_content)
        skill_dir = _unique_skill_dir(upload_dir, _safe_skill_dir_name(name))
        _copy_skill_contents(skill_md_path.parent, skill_dir)

    return PreparedSkillBundle(
        name=name,
        description=description,
        usage_rules=usage_rules,
        when_to_use=when_to_use,
        avoid_when=avoid_when,
        instructions=skill_md_content,
        skill_dir=skill_dir,
    )

def parse_skill_markdown(content: str):
    """Enhanced parser to handle both header-based and frontmatter-like Skill formatting."""
    name = "Unnamed Skill"
    description = ""
    usage_rules = ""
    when_to_use = ""
    avoid_when = ""
    
    # Try to extract frontmatter-like block (delimited by ---)
    frontmatter_match = re.search(r'---\s*(.*?)\s*---', content, re.DOTALL)
    if frontmatter_match:
        block = frontmatter_match.group(1)
        # Parse name
        name_match = re.search(r'name:\s*([^\n]+)', block)
        if name_match:
            name = name_match.group(1).strip()
        
        # Parse description
        desc_match = re.search(r'description:\s*"([^"]+)"', block)
        if desc_match:
            description = desc_match.group(1).strip()
        else:
            # Fallback if no quotes
            desc_match = re.search(r'description:\s*([^\n]+)', block)
            if desc_match:
                description = desc_match.group(1).strip()
                
        # Parse usage rules
        usage_match = re.search(r'usage_rules:\s*([^\n]+)', block)
        if usage_match:
            usage_rules = usage_match.group(1).strip()

        # Parse when_to_use
        when_match = re.search(r'when_to_use:\s*([^\n]+)', block)
        if when_match:
            when_to_use = when_match.group(1).strip()

        # Parse avoid_when
        avoid_match = re.search(r'avoid_when:\s*([^\n]+)', block)
        if avoid_match:
            avoid_when = avoid_match.group(1).strip()

        # If we found at least a name, we can return early or keep parsing for more info
        if name != "Unnamed Skill" and description:
            # If there's content after the frontmatter, use it for instructions
            remaining = content[frontmatter_match.end():].strip()
            return name, description, usage_rules, when_to_use, avoid_when

    # Fallback to header-based parsing
    lines = content.split('\n')
    current_section = None
    
    for line in lines:
        line_stripped = line.strip()
        if line_stripped.startswith("# "):
            if name == "Unnamed Skill":
                name = line_stripped[2:].strip()
        elif line_stripped.lower().startswith("## description"):
            current_section = "description"
        elif line_stripped.lower().startswith("## when to use") or line_stripped.lower().startswith("## usage"):
            current_section = "when_to_use"
        elif line_stripped.lower().startswith("## avoid when"):
            current_section = "avoid_when"
        elif line_stripped.lower().startswith("## usage rules"):
            current_section = "usage_rules"
        elif line_stripped.startswith("## "):
            current_section = "other"
        else:
            if current_section == "description" and line_stripped:
                description += line + "\n"
            elif current_section == "when_to_use" and line_stripped:
                when_to_use += line + "\n"
            elif current_section == "avoid_when" and line_stripped:
                avoid_when += line + "\n"
            elif current_section == "usage_rules" and line_stripped:
                usage_rules += line + "\n"
                
    return name, description.strip(), usage_rules.strip(), when_to_use.strip(), avoid_when.strip()

@router.post("/admin/skills", response_model=SkillOut)
async def upload_skill(
    file: UploadFile = File(...),
    session: AsyncSession = Depends(get_session),
    _=Depends(verify_admin)
):
    filename = file.filename or ""
    if not filename.lower().endswith(".zip"):
        raise HTTPException(status_code=400, detail="Only .zip files are allowed")

    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    temp_zip_path = UPLOAD_DIR / f"temp_{Path(filename).name}"
    
    try:
        with open(temp_zip_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
            
        # Check zip size
        if temp_zip_path.stat().st_size > 50 * 1024 * 1024: # 50MB limit
            raise HTTPException(status_code=400, detail="Zip file too large")
        
        bundle = prepare_skill_bundle(temp_zip_path, UPLOAD_DIR)
        
        # Check duplicate name
        existing_skill_result = await session.execute(select(Skill).where(Skill.name == bundle.name))
        existing_skill = existing_skill_result.scalars().first()
        if existing_skill:
            if existing_skill.file_path and os.path.exists(existing_skill.file_path):
                shutil.rmtree(existing_skill.file_path)
            existing_skill.description = bundle.description
            existing_skill.usage_rules = bundle.usage_rules
            existing_skill.when_to_use = bundle.when_to_use
            existing_skill.avoid_when = bundle.avoid_when
            existing_skill.instructions = bundle.instructions
            existing_skill.file_path = str(bundle.skill_dir)
            await session.commit()
            await session.refresh(existing_skill)
            await sync_all_codex_accounts(session)
            await create_admin_action(
                session,
                action="skill_update",
                target_type="skill",
                target_id=existing_skill.id,
                metadata={"name": existing_skill.name, "via": "upload"},
                commit=True
            )
            return serialize_skill(existing_skill)

        # Save to DB
        new_skill = Skill(
            name=bundle.name,
            description=bundle.description,
            usage_rules=bundle.usage_rules,
            when_to_use=bundle.when_to_use,
            avoid_when=bundle.avoid_when,
            instructions=bundle.instructions,
            file_path=str(bundle.skill_dir),
            is_active=True
        )
        session.add(new_skill)
        await session.commit()
        await session.refresh(new_skill)

        # Sync to Codex accounts
        await sync_all_codex_accounts(session)

        await create_admin_action(
            session,
            action="skill_upload",
            target_type="skill",
            target_id=new_skill.id,
            metadata={"name": new_skill.name},
            commit=True
        )
        
        return serialize_skill(new_skill)
        
    finally:
        if temp_zip_path.exists():
            temp_zip_path.unlink()

@router.get("/admin/skills", response_model=List[SkillOut])
async def list_skills(
    session: AsyncSession = Depends(get_session),
    _=Depends(verify_admin)
):
    result = await session.execute(select(Skill).order_by(Skill.created_at.desc()))
    return [serialize_skill(skill) for skill in result.scalars().all()]

@router.patch("/admin/skills/{skill_id}", response_model=SkillOut)
async def update_skill(
    skill_id: int,
    skill_update: SkillUpdate,
    session: AsyncSession = Depends(get_session),
    _=Depends(verify_admin)
):
    result = await session.execute(select(Skill).where(Skill.id == skill_id))
    skill = result.scalars().first()
    if not skill:
        raise HTTPException(status_code=404, detail="Skill not found")
        
    if skill_update.name is not None:
        skill.name = skill_update.name
    if skill_update.description is not None:
        skill.description = skill_update.description
    if skill_update.usage_rules is not None:
        skill.usage_rules = skill_update.usage_rules
    if skill_update.is_active is not None:
        skill.is_active = skill_update.is_active
        
    await session.commit()
    await session.refresh(skill)

    # Sync to Codex accounts
    await sync_all_codex_accounts(session)

    await create_admin_action(
        session,
        action="skill_update",
        target_type="skill",
        target_id=skill.id,
        metadata={"name": skill.name},
        commit=True
    )

    return serialize_skill(skill)

@router.delete("/admin/skills/{skill_id}")
async def delete_skill(
    skill_id: int,
    session: AsyncSession = Depends(get_session),
    _=Depends(verify_admin)
):
    result = await session.execute(select(Skill).where(Skill.id == skill_id))
    skill = result.scalars().first()
    if not skill:
        raise HTTPException(status_code=404, detail="Skill not found")
        
    if skill.file_path and os.path.exists(skill.file_path):
        shutil.rmtree(skill.file_path)
        
    await create_admin_action(
        session,
        action="skill_delete",
        target_type="skill",
        target_id=skill.id,
        metadata={"name": skill.name},
        commit=False
    )

    await session.delete(skill)
    await session.commit()

    # Sync to Codex accounts (removes deleted skill from account directories)
    async with async_session() as new_session:
        await sync_all_codex_accounts(new_session)

    return {"message": "Skill deleted successfully"}
