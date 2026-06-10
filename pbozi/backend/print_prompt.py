import asyncio
from sqlalchemy.future import select
from app.database import async_session
from app.models import SystemPrompt

async def main():
    async with async_session() as session:
        result = await session.execute(select(SystemPrompt).where(SystemPrompt.name == "default"))
        prompt = result.scalar_one_or_none()
        if prompt:
            print("=== DB CONTENT ===")
            print(prompt.content)
        else:
            print("No default prompt in DB.")

asyncio.run(main())
