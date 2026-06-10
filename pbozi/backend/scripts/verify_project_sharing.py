import asyncio
import os
import sys
import tempfile

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from app.models import Base, Document, Project, UserPreference
from app.services.project_sharing import (
    build_project_instructions_prompt,
    copy_project_for_user,
    ensure_project_share_token,
    list_visible_projects,
)


async def main():
    with tempfile.TemporaryDirectory() as tmpdir:
        engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        source_path = os.path.join(tmpdir, "source-notes.txt")
        with open(source_path, "w", encoding="utf-8") as handle:
            handle.write("source file body")

        async with session_factory() as db:
            owner = UserPreference(telegram_user_id=101, account_status="active")
            recipient = UserPreference(telegram_user_id=202, account_status="active")
            ali = UserPreference(telegram_user_id=303, account_status="active")
            global_project = Project(name="Legacy Ownerless")
            source = Project(
                name="Source",
                description="Project description",
                instructions="Always answer from this project first.",
                owner_user_id=1,
            )
            ali_project = Project(name="Ali Private", owner_user_id=1)
            db.add_all([owner, recipient, ali, global_project, source, ali_project])
            await db.flush()
            source.owner_user_id = owner.id
            ali_project.owner_user_id = ali.id
            doc = Document(
                project_id=source.id,
                filename="source-notes.txt",
                file_type="txt",
                file_path=source_path,
                chunk_count=3,
            )
            db.add(doc)
            await db.commit()
            await db.refresh(owner)
            await db.refresh(recipient)
            await db.refresh(source)

            token = await ensure_project_share_token(db, source)
            assert token == source.share_token
            assert len(token) >= 20

            visible = await list_visible_projects(db, ali)
            assert [project.name for project in visible] == ["Ali Private"]

            copied = await copy_project_for_user(db, token=token, recipient=recipient, upload_root=tmpdir)
            assert copied.name == "Source"
            assert copied.description == "Project description"
            assert copied.instructions == "Always answer from this project first."
            assert copied.owner_user_id == recipient.id
            assert copied.shared_from_project_id == source.id

            copied_docs = (
                await db.execute(select(Document).where(Document.project_id == copied.id))
            ).scalars().all()
            assert len(copied_docs) == 1
            assert copied_docs[0].filename == "source-notes.txt"
            assert copied_docs[0].chunk_count == 3
            assert os.path.exists(copied_docs[0].file_path)
            with open(copied_docs[0].file_path, "r", encoding="utf-8") as handle:
                assert handle.read() == "source file body"

            copied_again = await copy_project_for_user(db, token=token, recipient=recipient, upload_root=tmpdir)
            assert copied_again.id == copied.id

            prompt = build_project_instructions_prompt(copied)
            assert "Project instructions" in prompt
            assert "Always answer from this project first." in prompt

        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
