from alembic import context
from sqlalchemy import create_engine, text

from app.core.config import settings
from app.models import Base

target_metadata = Base.metadata


def _include(obj, name, type_, reflected, compare_to):
    return True


def run_migrations_online() -> None:
    engine = create_engine(settings.database_url)
    with engine.connect() as conn:
        if conn.dialect.name == "postgresql":
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
            conn.commit()
        context.configure(connection=conn, target_metadata=target_metadata, compare_type=True)
        with context.begin_transaction():
            context.run_migrations()


run_migrations_online()
