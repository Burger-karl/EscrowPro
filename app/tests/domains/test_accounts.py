import uuid
from fastapi.testclient import TestClient

from app.tests.conftest import auth_header


def test_register_client_success(client: TestClient):
    email = f"ada_{uuid.uuid4().hex[:8]}@paywork.dev"
    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": "Password123!",
            "full_name": "Ada Lovelace",
            "role": "client",
        },
    )
    assert response.status_code == 201
    data = response.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["user"]["email"] == email
    assert data["user"]["role"] == "client"


def test_register_freelancer_success(client: TestClient):
    email = f"femi_{uuid.uuid4().hex[:8]}@paywork.dev"
    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": "Password123!",
            "full_name": "Femi Freelancer",
            "role": "freelancer",
        },
    )
    assert response.status_code == 201
    data = response.json()
    assert data["user"]["role"] == "freelancer"


def test_register_arbiter_public_rejected(client: TestClient):
    email = f"arbiter_{uuid.uuid4().hex[:8]}@paywork.dev"
    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": "Password123!",
            "full_name": "Public Rogue",
            "role": "arbiter",
        },
    )
    assert response.status_code == 422


def test_register_duplicate_email_returns_409(client: TestClient):
    email = f"dup_{uuid.uuid4().hex[:8]}@paywork.dev"
    payload = {
        "email": email,
        "password": "Password123!",
        "full_name": "Duplicate User",
        "role": "client",
    }
    res1 = client.post("/api/v1/auth/register", json=payload)
    assert res1.status_code == 201

    res2 = client.post("/api/v1/auth/register", json=payload)
    assert res2.status_code == 409
    assert res2.json()["error"]["code"] == "email_taken"


def test_login_success(client: TestClient):
    email = f"login_{uuid.uuid4().hex[:8]}@paywork.dev"
    client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": "Password123!",
            "full_name": "Login User",
            "role": "client",
        },
    )
    res = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "Password123!"},
    )
    assert res.status_code == 200
    assert "access_token" in res.json()


def test_login_wrong_password_returns_401(client: TestClient):
    email = f"wrong_{uuid.uuid4().hex[:8]}@paywork.dev"
    client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": "Password123!",
            "full_name": "Wrong User",
            "role": "client",
        },
    )
    res = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "WrongPassword!"},
    )
    assert res.status_code == 401
    assert res.json()["error"]["code"] == "invalid credentials"


def test_refresh_token_success(client: TestClient):
    email = f"refresh_{uuid.uuid4().hex[:8]}@paywork.dev"
    reg = client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": "Password123!",
            "full_name": "Refresh User",
            "role": "client",
        },
    ).json()

    res = client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": reg["refresh_token"]},
    )
    assert res.status_code == 200
    assert "access_token" in res.json()


def test_admin_can_create_arbiter(client: TestClient, admin_token: str):
    email = f"arbiter_{uuid.uuid4().hex[:8]}@paywork.dev"
    res = client.post(
        "/api/v1/auth/users",
        headers=auth_header(admin_token),
        json={
            "email": email,
            "password": "Password123!",
            "full_name": "Bola Arbiter",
            "role": "arbiter",
        },
    )
    assert res.status_code == 201
    assert res.json()["role"] == "arbiter"


def test_non_admin_cannot_create_arbiter(client: TestClient, client_token: str):
    email = f"arbiter_{uuid.uuid4().hex[:8]}@paywork.dev"
    res = client.post(
        "/api/v1/auth/users",
        headers=auth_header(client_token),
        json={
            "email": email,
            "password": "Password123!",
            "full_name": "Rogue Arbiter",
            "role": "arbiter",
        },
    )
    assert res.status_code == 403


def test_list_freelancers_authenticated(client: TestClient, client_token: str, freelancer_user):
    res = client.get("/api/v1/freelancers", headers=auth_header(client_token))
    assert res.status_code == 200
    assert isinstance(res.json(), list)
    emails = [f["email"] for f in res.json()]
    assert freelancer_user.email in emails
