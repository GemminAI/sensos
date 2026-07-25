from contextlib import contextmanager
from typing import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from runtime.core.config import Settings, get_settings
from runtime.db.tables import Base

_engine = None
_SessionLocal = None


def init_db(settings: Settings | None = None) -> None:
    global _engine, _SessionLocal
    settings = settings or get_settings()
    _engine = create_engine(settings.database_url, pool_pre_ping=True)
    _SessionLocal = sessionmaker(bind=_engine, autocommit=False, autoflush=False)
    Base.metadata.create_all(bind=_engine)


def get_engine():
    if _engine is None:
        init_db()
    return _engine


@contextmanager
def get_db_session() -> Generator[Session, None, None]:
    if _SessionLocal is None:
        init_db()
    session = _SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
