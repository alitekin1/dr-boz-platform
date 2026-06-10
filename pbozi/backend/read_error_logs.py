
import asyncio
from sqlalchemy import select
from app.database import async_session
from app.models import ErrorLog

async def read_errors():
    async with async_session() as session:
        result = await session.execute(select(ErrorLog).order_by(ErrorLog.timestamp.desc()).limit(10))
        errors = result.scalars().all()
        for err in errors:
            print(f"--- {err.timestamp} [{err.source}] ---")
            print(f"Message: {err.error_message}")
            print(f"Stack Trace: {err.stack_trace}")
            print("-" * 40)

if __name__ == "__main__":
    asyncio.run(read_errors())
