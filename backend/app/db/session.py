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

_DATABASE_URL: str = settings.DATABASE_URL

engine = create_engine(_DATABASE_URL, pool_pre_ping=True)

SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency that yields a DB session and closes it after use."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
