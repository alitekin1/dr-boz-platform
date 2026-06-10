import asyncio
from app.database import async_session
from app.services.codex_skill_sync import sync_all_codex_accounts

async def main():
    async with async_session() as db:
        print("Starting sync of all Codex accounts...")
        await sync_all_codex_accounts(db)
        print("Sync complete.")

if __name__ == "__main__":
    asyncio.run(main())
