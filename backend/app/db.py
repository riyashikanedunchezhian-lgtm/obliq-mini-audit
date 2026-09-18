from __future__ import annotations

import os
from collections.abc import Generator

from sqlalchemy.orm import Session

from app.models import init_db, make_engine, session_factory

_ENGINE = None
_SessionLocal = None


def get_engine():
    global _ENGINE, _SessionLocal
    if _ENGINE is None:
        db_url = os.environ.get("DATABASE_URL")
        _ENGINE = make_engine(db_url)
        init_db(_ENGINE)
        _SessionLocal = session_factory(_ENGINE)
    return _ENGINE


def get_session_factory():
    get_engine()
    return _SessionLocal


def get_db() -> Generator[Session, None, None]:
    SessionLocal = get_session_factory()
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def reset_engine() -> None:
    """Used by tests to swap in a throwaway database."""
    global _ENGINE, _SessionLocal
    _ENGINE = None
    _SessionLocal = None
