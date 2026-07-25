from contextlib import contextmanager
from typing import Generator

from fastapi import Depends
from sqlalchemy.orm import Session

from runtime.db.session import get_db_session


@contextmanager
def db_session() -> Generator[Session, None, None]:
    with get_db_session() as session:
        yield session


def get_db() -> Generator[Session, None, None]:
    with get_db_session() as session:
        yield session
