import asyncio
from app.telegram_bot.handlers.posts import _extract_media_id_from_url
from app.database import engine, Base
from sqlalchemy.ext.asyncio import create_async_engine

async def test_all():
    # 1. Test URL extraction
    url = "https://www.instagram.com/p/C-1234abcd/"
    media_id = _extract_media_id_from_url(url)
    assert media_id == "C-1234abcd", f"Extraction failed: {media_id}"
    print("✅ URL extraction passed:", media_id)
    
    # 2. Test DB connection
    # using the local engine from app.database, or create a simple memory one to test schema
    test_engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print("✅ Database (mock) tables created successfully")

    print("All tests passed.")

if __name__ == "__main__":
    asyncio.run(test_all())
