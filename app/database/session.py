from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from app.core.config import settings
from app.database.models import Base

engine = create_async_engine(settings.get_database_url(), echo=False)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


def _add_invitation_song_columns(conn):
    """Añade columnas de invitación por canciones si no existen (migración SQLite)."""
    db_url = settings.get_database_url()
    for col, spec in [
        ("song_quota", "INTEGER"),
        ("songs_used", "INTEGER DEFAULT 0"),
        ("first_used_at", "DATETIME"),
        ("gate_expires_at", "DATETIME"),
    ]:
        try:
            conn.execute(text(f"ALTER TABLE invitations ADD COLUMN {col} {spec}"))
        except Exception:
            pass


def _add_user_and_invitation_columns(conn):
    """Añade columnas nuevas a users e invitations (migración SQLite)."""
    db_url = settings.get_database_url()
    for table, cols in [
        ("users", [("first_name", "VARCHAR(255)"), ("last_name", "VARCHAR(255)")]),
        (
            "invitations",
            [
                ("registered_at", "DATETIME"),
                ("invitee_first_name", "VARCHAR(255)"),
                ("invitee_last_name", "VARCHAR(255)"),
                ("access_type", "VARCHAR(50)"),
            ],
        ),
    ]:
        for col, spec in cols:
            try:
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {col} {spec}"))
            except Exception:
                pass


async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        db_url = settings.get_database_url()
        if "sqlite" in (db_url or ""):
            await conn.run_sync(_add_invitation_song_columns)
            await conn.run_sync(_add_user_and_invitation_columns)

async def get_db():
    async with AsyncSessionLocal() as session:
        yield session
