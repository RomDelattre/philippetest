import os
from collections.abc import Iterator
from pathlib import Path

os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("AUTH_MODE", "dev")
os.environ.setdefault("DATABASE_URL", "sqlite://")

import pytest  # noqa: E402
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy.engine import Engine  # noqa: E402
from sqlalchemy.orm import Session, sessionmaker  # noqa: E402

from app.config import get_settings  # noqa: E402
from app.db import get_session, make_engine  # noqa: E402
from app.main import app  # noqa: E402
from app.seed import seed_anonymous_technicians, seed_reference  # noqa: E402

BACKEND_DIR = Path(__file__).resolve().parents[1]


def alembic_config(url: str) -> Config:
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    cfg.set_main_option("sqlalchemy.url", url)
    cfg.attributes["skip_logging"] = True
    return cfg


@pytest.fixture
def engine(tmp_path: Path) -> Iterator[Engine]:
    """Base SQLite neuve, construite par les migrations (et non par create_all)."""
    url = f"sqlite:///{tmp_path / 'test.db'}"
    command.upgrade(alembic_config(url), "head")
    eng = make_engine(url)
    yield eng
    eng.dispose()


@pytest.fixture
def session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


@pytest.fixture
def session(session_factory: sessionmaker[Session]) -> Iterator[Session]:
    with session_factory() as s:
        yield s


@pytest.fixture
def seeded(session: Session) -> Session:
    seed_reference(session)
    seed_anonymous_technicians(session)
    session.commit()
    return session


@pytest.fixture
def client(session_factory: sessionmaker[Session], seeded: Session) -> Iterator[TestClient]:
    def _override() -> Iterator[Session]:
        with session_factory() as s:
            yield s

    app.dependency_overrides[get_session] = _override
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
    get_settings.cache_clear()
