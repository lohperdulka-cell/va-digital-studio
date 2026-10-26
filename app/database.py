"""Database engine, session factory and declarative base."""

from __future__ import annotations

from collections.abc import Generator, Iterator
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import BASE_DIR, settings


class Base(DeclarativeBase):
    """Declarative base for every ORM model."""


def _sqlite_file_parent() -> Path:
    """Directory holding the SQLite file, resolved the same way config does."""
    path = Path(settings.sqlite_path)
    if not path.is_absolute():
        path = (BASE_DIR / path).resolve()
    return path.parent


def _build_engine() -> Engine:
    url = settings.sqlalchemy_url
    if settings.is_sqlite:
        # The file lives in ./data by default, which a fresh checkout does not
        # have; create it so the SQLite fallback works without a manual step.
        _sqlite_file_parent().mkdir(parents=True, exist_ok=True)
        engine = create_engine(
            url,
            # SQLite only: FastAPI serves requests from a thread pool.
            connect_args={"check_same_thread": False},
            pool_pre_ping=True,
        )

        @event.listens_for(engine, "connect")
        def _set_sqlite_pragmas(dbapi_connection, _record) -> None:
            cursor = dbapi_connection.cursor()
            # ON DELETE CASCADE and CHECK constraints are otherwise ignored.
            cursor.execute("PRAGMA foreign_keys=ON")
            # WAL keeps readers from blocking the single writer.
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.close()

        return engine

    # pool_pre_ping survives the dropped connections a cloud proxy produces;
    # pool_recycle retires a connection before the proxy's own idle timeout.
    return create_engine(
        url,
        pool_pre_ping=True,
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_max_overflow,
        pool_recycle=settings.db_pool_recycle,
    )


engine: Engine = _build_engine()

SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
    expire_on_commit=False,
    class_=Session,
)


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency yielding a request-scoped session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@contextmanager
def session_scope() -> Iterator[Session]:
    """Transactional scope for scripts, CLI commands and background tasks."""
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
