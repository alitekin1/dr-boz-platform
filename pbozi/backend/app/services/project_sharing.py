import logging
import os
import secrets
import shutil

from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Document, Project, ProjectGroupShare, UserPreference

logger = logging.getLogger(__name__)

PROJECT_SHARE_TOKEN_BYTES = 18
PROJECT_SHARE_START_PREFIX = "pshare_"


def _generate_share_token() -> str:
    return secrets.token_urlsafe(PROJECT_SHARE_TOKEN_BYTES)


def _project_upload_dir(upload_root: str, project_id: int) -> str:
    return os.path.join(upload_root, f"project_{project_id}")


def _unique_destination_path(directory: str, filename: str) -> str:
    safe_name = os.path.basename(filename or "document")
    stem, ext = os.path.splitext(safe_name)
    candidate = os.path.join(directory, safe_name)
    counter = 1
    while os.path.exists(candidate):
        candidate = os.path.join(directory, f"{stem}_{counter}{ext}")
        counter += 1
    return candidate


async def ensure_project_share_token(db: AsyncSession, project: Project) -> str:
    if project.share_token:
        return project.share_token

    for _ in range(5):
        project.share_token = _generate_share_token()
        try:
            await db.commit()
            await db.refresh(project)
            return project.share_token
        except IntegrityError:
            await db.rollback()
            await db.refresh(project)
            project.share_token = None

    raise ValueError("Could not create a unique project share token")


async def get_project_by_share_token(db: AsyncSession, token: str) -> Project | None:
    token = (token or "").strip()
    if not token:
        return None
    result = await db.execute(select(Project).where(Project.share_token == token))
    return result.scalar_one_or_none()


async def share_project_with_group(db: AsyncSession, project_id: int, group_id: int, shared_by_user_id: int) -> ProjectGroupShare:
    existing = (
        await db.execute(
            select(ProjectGroupShare).where(
                ProjectGroupShare.project_id == project_id,
                ProjectGroupShare.group_id == group_id,
            )
        )
    ).scalar_one_or_none()
    if existing:
        return existing

    share = ProjectGroupShare(
        project_id=project_id,
        group_id=group_id,
        shared_by_user_id=shared_by_user_id,
    )
    db.add(share)
    await db.commit()
    await db.refresh(share)
    return share


async def list_group_shared_projects(db: AsyncSession, group_id: int) -> list[Project]:
    query = (
        select(Project)
        .join(ProjectGroupShare, ProjectGroupShare.project_id == Project.id)
        .where(ProjectGroupShare.group_id == group_id)
        .order_by(Project.created_at.desc(), Project.id.desc())
    )
    return (await db.execute(query)).scalars().all()


async def list_visible_projects(db: AsyncSession, user: UserPreference) -> list[Project]:
    if not user.is_admin and not user.is_pro:
        return []
    query = select(Project).where(Project.owner_user_id == user.id)
    query = query.order_by(Project.created_at.desc(), Project.id.desc())
    return (await db.execute(query)).scalars().all()


async def list_group_public_projects(db: AsyncSession) -> list[Project]:
    query = (
        select(Project)
        .where(
            or_(
                Project.owner_user_id.is_(None),
                Project.share_token.is_not(None),
            )
        )
        .order_by(Project.created_at.desc(), Project.id.desc())
    )
    return (await db.execute(query)).scalars().all()


async def get_group_public_project(db: AsyncSession, project_id: int, group_id: int | None = None) -> Project | None:
    if group_id:
        query = (
            select(Project)
            .join(ProjectGroupShare, ProjectGroupShare.project_id == Project.id)
            .where(
                Project.id == project_id,
                ProjectGroupShare.group_id == group_id,
            )
        )
    else:
        query = (
            select(Project)
            .where(
                Project.id == project_id,
                or_(
                    Project.owner_user_id.is_(None),
                    Project.share_token.is_not(None),
                ),
            )
        )
    return (await db.execute(query)).scalar_one_or_none()


async def user_can_access_project(db: AsyncSession, user: UserPreference, project_id: int) -> Project | None:
    if not user.is_admin and not user.is_pro:
        return None
    query = select(Project).where(Project.id == project_id)
    if not user.is_admin:
        query = query.where(Project.owner_user_id == user.id)
    return (await db.execute(query)).scalar_one_or_none()


def build_project_instructions_prompt(project: Project | None) -> str:
    if not project:
        return ""

    description = (project.description or "").strip()
    instructions = (project.instructions or "").strip()
    if not description and not instructions:
        return ""

    lines = ["Project instructions for this chat:"]
    if description:
        lines.append(f"- Description: {description}")
    if instructions:
        lines.append(f"- Instructions: {instructions}")
    lines.append("- Treat these as project-specific guidance unless the user explicitly overrides them.")
    return "\n".join(lines)


async def copy_project_for_user(
    db: AsyncSession,
    *,
    token: str,
    recipient: UserPreference,
    upload_root: str = "./uploads",
) -> Project:
    source = await get_project_by_share_token(db, token)
    if not source:
        raise ValueError("Project share link is invalid or expired")

    existing = (
        await db.execute(
            select(Project).where(
                Project.owner_user_id == recipient.id,
                Project.shared_from_project_id == source.id,
            )
        )
    ).scalar_one_or_none()
    if existing:
        return existing

    copied = Project(
        name=source.name,
        description=source.description,
        instructions=source.instructions,
        owner_user_id=recipient.id,
        shared_from_project_id=source.id,
    )
    db.add(copied)
    await db.flush()

    target_dir = _project_upload_dir(upload_root, copied.id)
    os.makedirs(target_dir, exist_ok=True)

    source_docs = (
        await db.execute(select(Document).where(Document.project_id == source.id).order_by(Document.id))
    ).scalars().all()
    document_id_map: dict[int, int] = {}
    for source_doc in source_docs:
        target_path = None
        if not source_doc.file_path or not os.path.exists(source_doc.file_path):
            logger.warning("Project file is missing for copy: %s (path=%s). Skipping physical copy, but will attempt to map chunks.", 
                           source_doc.filename or source_doc.id, source_doc.file_path)
        else:
            try:
                target_path = _unique_destination_path(target_dir, source_doc.filename or os.path.basename(source_doc.file_path))
                shutil.copy2(source_doc.file_path, target_path)
            except Exception:
                logger.exception("Failed to copy project file: %s", source_doc.file_path)
                target_path = None

        copied_doc = Document(
            project_id=copied.id,
            filename=os.path.basename(target_path) if target_path else (source_doc.filename or f"missing_{source_doc.id}"),
            file_type=source_doc.file_type,
            file_path=target_path,
            chunk_count=source_doc.chunk_count,
            status="indexed" if target_path is None and source_doc.chunk_count > 0 else "pending",
        )
        db.add(copied_doc)
        await db.flush()
        document_id_map[source_doc.id] = copied_doc.id

    await db.commit()
    await db.refresh(copied)

    try:
        from app.llm import get_emb_config
        from app.rag import copy_project_index

        emb = await get_emb_config(db)
        copied_chunks = copy_project_index(
            source.id,
            copied.id,
            document_id_map,
            api_key=emb.api_key if emb else None,
            model=emb.model if emb else None,
        )
        if copied_chunks:
            logger.info("Copied %s indexed chunks for shared project %s -> %s", copied_chunks, source.id, copied.id)
    except Exception:
        logger.exception("Could not copy Chroma index for shared project %s -> %s", source.id, copied.id)

    return copied
