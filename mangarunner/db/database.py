import os
from pathlib import Path
from typing import Generator
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, Session
from mangarunner.db.models import Base

_engine = None
_session_factory = None

def get_database_url(db_path: str = "./data/mangarunner.db") -> str:
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    abs_path = path.resolve()
    posix_path = abs_path.as_posix()
    return f"sqlite:///{posix_path}"

def get_engine(db_path: str = "./data/mangarunner.db"):
    global _engine, _session_factory
    if _engine is None:
        db_url = get_database_url(db_path)
        _engine = create_engine(
            db_url,
            echo=False,
            future=True,
            connect_args={"check_same_thread": False},
        )
        _session_factory = sessionmaker(
            bind=_engine,
            class_=Session,
            expire_on_commit=False,
        )
    return _engine

def get_session_factory(db_path: str = "./data/mangarunner.db") -> sessionmaker[Session]:
    global _session_factory
    if _session_factory is None:
        get_engine(db_path)
    return _session_factory

def init_db(db_path: str = "./data/mangarunner.db") -> None:
    """Initialize database tables and enable WAL mode."""
    engine = get_engine(db_path)
    with engine.begin() as conn:
        conn.execute(text("PRAGMA journal_mode = WAL;"))
        conn.execute(text("PRAGMA foreign_keys = ON;"))
        Base.metadata.create_all(conn)

def get_db_session() -> Generator[Session, None, None]:
    """Dependency for API routes needing DB access."""
    session_factory = get_session_factory()
    with session_factory() as session:
        try:
            yield session
        finally:
            session.close()
