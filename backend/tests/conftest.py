import os
from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

# Ensure test environment
os.environ["APP_ENV"] = "test"
os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["LLM_PROVIDER"] = "mock"
os.environ["EMBEDDING_PROVIDER"] = "fake"
os.environ["EMBEDDING_MODEL"] = "mock-embed-384"
os.environ["EMBEDDING_DIMENSIONS"] = "384"
os.environ["SANDBOX_PROVIDER"] = "mock"
os.environ["BILLING_PROVIDER"] = "mock"

from app.core.config import settings  # noqa: E402

settings.LLM_PROVIDER = "mock"
settings.EMBEDDING_PROVIDER = "fake"
settings.EMBEDDING_MODEL = "mock-embed-384"
settings.EMBEDDING_DIMENSIONS = 384
settings.SANDBOX_PROVIDER = "mock"
settings.BILLING_PROVIDER = "mock"

from app.core.rate_limit import auth_rate_limiter  # noqa: E402
from app.db.base import Base  # noqa: E402
from app.db.session import get_db  # noqa: E402
from app.main import app  # noqa: E402

TEST_DATABASE_URL = "sqlite:///:memory:"
test_engine = create_engine(
    TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(
    autocommit=False, autoflush=False, bind=test_engine, expire_on_commit=False
)


@pytest.fixture(scope="session", autouse=True)
def setup_database():
    """Create all tables in the test database once per session."""
    Base.metadata.create_all(bind=test_engine)
    yield
    Base.metadata.drop_all(bind=test_engine)


@pytest.fixture
def db() -> Generator[Session, None, None]:
    """Provide a clean database session per test."""
    session = TestingSessionLocal()
    yield session
    # Cleanup database tables after each test
    session.rollback()
    for table in reversed(Base.metadata.sorted_tables):
        session.execute(table.delete())
    session.commit()
    session.close()


@pytest.fixture(autouse=True)
def reset_rate_limiter():
    """Reset the auth rate limiter between tests."""
    auth_rate_limiter.reset()


@pytest.fixture
def client(db: Session) -> Generator[TestClient, None, None]:
    """TestClient wired to use the test database session."""

    def override_get_db():
        try:
            yield db
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app, cookies={}) as test_client:
        yield test_client
    app.dependency_overrides.clear()
