"""
app/db/session.py

SQLAlchemy session factory and FastAPI dependency.

Default: SQLite file at ./kanggaemi.db (development).
For production, set DATABASE_URL in .env:
  DATABASE_URL=postgresql+psycopg2://user:pass@host/dbname
"""
from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings

_DATABASE_URL: str = getattr(settings, "DATABASE_URL", "sqlite:///./kanggaemi.db")

engine = create_engine(
    _DATABASE_URL,
    # SQLite-specific: allow multi-threaded access (needed for FastAPI)
    connect_args={"check_same_thread": False} if _DATABASE_URL.startswith("sqlite") else {},
)

SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency that yields a DB session and closes it after use."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
