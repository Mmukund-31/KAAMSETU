"""Shared fixtures.

Tests run against a dedicated PostgreSQL database (DATABASE_URL_TEST, default: <main db>_test).
The schema is built with the real Alembic migrations, so every run also tests the migrations.
Each test runs inside a transaction that is rolled back afterwards (services may call commit();
that only releases a SAVEPOINT).
"""

import os

os.environ["APP_ENV"] = "test"
os.environ["RATE_LIMIT_ENABLED"] = "false"

from collections.abc import Callable, Iterator  # noqa: E402
from dataclasses import dataclass  # noqa: E402
from pathlib import Path  # noqa: E402

import pytest  # noqa: E402
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import Engine, create_engine, text  # noqa: E402
from sqlalchemy.engine import make_url  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.config import BACKEND_DIR, get_settings  # noqa: E402
from app.core.rate_limit import limiter  # noqa: E402
from app.core.security import create_access_token, hash_password  # noqa: E402
from app.database.session import get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.models import LanguageCode, Site, User, UserRole  # noqa: E402

TEST_PASSWORD = "TestPass123"


def alembic_config(url: str) -> Config:
    cfg = Config(str(Path(BACKEND_DIR) / "alembic.ini"))
    cfg.attributes["database_url"] = url
    cfg.attributes["configure_logger"] = False
    return cfg


def _ensure_database(url: str) -> None:
    target = make_url(url)
    admin = create_engine(target.set(database="postgres"), isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        exists = conn.scalar(text("SELECT 1 FROM pg_database WHERE datname = :n"), {"n": target.database})
        if not exists:
            conn.execute(text(f'CREATE DATABASE "{target.database}"'))
    admin.dispose()


@pytest.fixture(scope="session")
def test_database_url() -> str:
    url = get_settings().test_database_url
    assert make_url(url).database.endswith("_test"), "Refusing to run tests against a non-test database"
    return url


@pytest.fixture(scope="session")
def engine(test_database_url: str) -> Iterator[Engine]:
    _ensure_database(test_database_url)
    eng = create_engine(test_database_url)
    with eng.begin() as conn:  # start from an empty schema every session
        conn.execute(text("DROP SCHEMA public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))
    command.upgrade(alembic_config(test_database_url), "head")
    yield eng
    eng.dispose()


@pytest.fixture
def db(engine: Engine) -> Iterator[Session]:
    connection = engine.connect()
    outer = connection.begin()
    session = Session(bind=connection, join_transaction_mode="create_savepoint", expire_on_commit=False)
    try:
        yield session
    finally:
        session.close()
        outer.rollback()
        connection.close()


@pytest.fixture
def client(db: Session) -> Iterator[TestClient]:
    app.dependency_overrides[get_db] = lambda: db
    limiter.reset()
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def site(db: Session) -> Site:
    s = Site(name="Test Plant", location="Test City")
    db.add(s)
    db.flush()
    return s


@dataclass
class UserFactory:
    db: Session
    site: Site
    counter: int = 0

    def __call__(self, role: UserRole = UserRole.TECHNICIAN, *, active: bool = True, site: Site | None = None) -> User:
        self.counter += 1
        user = User(
            name=f"{role.value.title()} {self.counter}",
            email=f"{role.value}{self.counter}@test.local",
            password_hash=hash_password(TEST_PASSWORD),
            role=role,
            preferred_language=LanguageCode.EN,
            site_id=(site or self.site).id,
            is_active=active,
        )
        self.db.add(user)
        self.db.flush()
        return user


@pytest.fixture
def make_user(db: Session, site: Site) -> UserFactory:
    return UserFactory(db, site)


@pytest.fixture
def auth_headers() -> Callable[[User], dict[str, str]]:
    def build(user: User) -> dict[str, str]:
        token, _ = create_access_token(user.id, user.role.value)
        return {"Authorization": f"Bearer {token}"}

    return build
