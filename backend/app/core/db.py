from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings

# connect_timeout: fail in 10 seconds instead of hanging for minutes when the database is unreachable.
_args = {"connect_timeout": 10} if settings.database_url.startswith("postgresql") else {"check_same_thread": False}
engine = create_engine(settings.database_url, pool_pre_ping=True, pool_recycle=300, pool_size=5, max_overflow=10, connect_args=_args)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
