from datetime import datetime, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import settings


class Base(DeclarativeBase):
    pass


def utcnow() -> datetime:
    # Naive UTC everywhere: SQLite has no timezone type, and mixing aware/naive
    # datetimes is the classic comparison bug. Convert at the API edge if needed.
    return datetime.now(timezone.utc).replace(tzinfo=None)


engine = create_engine(settings.database_url, future=True)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False, future=True)
