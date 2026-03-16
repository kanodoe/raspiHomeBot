from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from app.core.config import settings
from app.database.models import Base

engine = create_async_engine(settings.DATABASE_URL, echo=False)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


def _add_invitation_song_columns(conn):
    """Añade columnas de invitación por canciones si no existen (migración SQLite)."""
    for col, spec in [
        ("song_quota", "INTEGER"),
        ("songs_used", "INTEGER DEFAULT 0"),
        ("first_used_at", "DATETIME"),
        ("gate_expires_at", "DATETIME"),
    ]:
        try:
            conn.execute(text(f"ALTER TABLE invitations ADD COLUMN {col} {spec}"))
        except Exception:
            pass  # Columna ya existe


async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        if "sqlite" in (settings.DATABASE_URL or ""):
            await conn.run_sync(_add_invitation_song_columns)

async def get_db():
    async with AsyncSessionLocal() as session:
        yield session
