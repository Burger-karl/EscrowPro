import os
os.environ["TESTING"] = "true"

import uuid
from collections.abc import Generator
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, create_engine, select

from app.core.config import settings
from app.core.dependencies import get_db
from app.core.security import create_access_token, hash_password
from app.main import app
from app.src.accounts.models import User, UserRole

# Shared test engine connected to the running PostgreSQL container
engine = create_engine(settings.DATABASE_URL, pool_pre_ping=True)


@pytest.fixture(autouse=True)
def mock_firestore():
    """Mock out external Firestore calls so tests are fully self-contained and fast."""
    with patch("app.src.disputes.firestore_client.create_thread") as m_create, \
         patch("app.src.disputes.firestore_client.add_message") as m_add, \
         patch("app.src.disputes.firestore_client.mark_thread_resolved") as m_resolve:
        yield {"create": m_create, "add": m_add, "resolve": m_resolve}


@pytest.fixture
def db_session() -> Generator[Session, None, None]:
    """Provides a transactional database session per test, rolling back any changes."""
    connection = engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection, join_transaction_mode="create_savepoint")

    yield session

    session.close()
    if transaction.is_active:
        transaction.rollback()
    connection.close()


@pytest.fixture
def client(db_session: Session) -> Generator[TestClient, None, None]:
    """TestClient configured with dependency overrides for database session."""
    def _override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def client_user(db_session: Session) -> User:
    email = f"client_{uuid.uuid4().hex[:8]}@paywork.dev"
    user = User(
        email=email,
        password_hash=hash_password("Password123!"),
        full_name="Test Client",
        role=UserRole.CLIENT,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture
def freelancer_user(db_session: Session) -> User:
    email = f"freelancer_{uuid.uuid4().hex[:8]}@paywork.dev"
    user = User(
        email=email,
        password_hash=hash_password("Password123!"),
        full_name="Test Freelancer",
        role=UserRole.FREELANCER,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture
def arbiter_user(db_session: Session) -> User:
    email = f"arbiter_{uuid.uuid4().hex[:8]}@paywork.dev"
    user = User(
        email=email,
        password_hash=hash_password("Password123!"),
        full_name="Test Arbiter",
        role=UserRole.ARBITER,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture
def finance_user(db_session: Session) -> User:
    email = f"finance_{uuid.uuid4().hex[:8]}@paywork.dev"
    user = User(
        email=email,
        password_hash=hash_password("Password123!"),
        full_name="Test Finance",
        role=UserRole.FINANCE,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture
def admin_user(db_session: Session) -> User:
    email = f"admin_{uuid.uuid4().hex[:8]}@paywork.dev"
    user = User(
        email=email,
        password_hash=hash_password("Password123!"),
        full_name="Test Admin",
        role=UserRole.ADMIN,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture
def client_token(client_user: User) -> str:
    return create_access_token(str(client_user.id), client_user.role.value)


@pytest.fixture
def freelancer_token(freelancer_user: User) -> str:
    return create_access_token(str(freelancer_user.id), freelancer_user.role.value)


@pytest.fixture
def arbiter_token(arbiter_user: User) -> str:
    return create_access_token(str(arbiter_user.id), arbiter_user.role.value)


@pytest.fixture
def finance_token(finance_user: User) -> str:
    return create_access_token(str(finance_user.id), finance_user.role.value)


@pytest.fixture
def admin_token(admin_user: User) -> str:
    return create_access_token(str(admin_user.id), admin_user.role.value)


def auth_header(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}
