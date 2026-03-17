import os
# Mock mandatory env vars for AppSettings initialization during tests
os.environ.setdefault("PC_MAC", "00:00:00:00:00:00")
os.environ.setdefault("PC_IP", "127.0.0.1")
os.environ.setdefault("SSH_USER", "test_user")
os.environ.setdefault("SSH_KEY_PATH", "/tmp/id_rsa")
os.environ.setdefault("ADMIN_TELEGRAM_ID", "12345")

import pytest_asyncio
import asyncio
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from app.database.models import Base

@pytest_asyncio.fixture(scope="session")
def event_loop():
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()

@pytest_asyncio.fixture
async def engine():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()

@pytest_asyncio.fixture
async def db_session(engine):
    async_session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with async_session() as session:
        yield session
        await session.rollback()
