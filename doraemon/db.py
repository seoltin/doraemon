from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from .config import settings
from pathlib import Path
import os

class Base(DeclarativeBase):
    pass

def _ensure_db_path():
    url = settings.database_url
    if url.startswith("sqlite+aiosqlite:///"):
        db_file = url.replace("sqlite+aiosqlite:///", "")
        if db_file.startswith("./"):
            db_file = db_file[2:]
        os.makedirs(os.path.dirname(db_file) or ".", exist_ok=True)

_ensure_db_path()

engine = create_async_engine(
    settings.database_url,
    echo=False,
    connect_args={"check_same_thread": False} if settings.database_url.startswith("sqlite") else {},
    future=True
)

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False
)

async def get_db():
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise

async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print("[DB] Database initialized successfully.")
