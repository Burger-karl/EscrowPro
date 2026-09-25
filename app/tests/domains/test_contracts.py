import uuid
from fastapi.testclient import TestClient

from app.tests.conftest import auth_header


def test_create_contract_client_success(
    client: TestClient, client_token: str, freelancer_user
):
    res = client.post(
        "/api/v1/contracts",
        headers=auth_header(client_token),
        json={
            "freelancer_email": freelancer_user.email,
            "title": "Build Web App",
            "description": "Fullstack development project",
            "milestones": [
                {
                    "title": "Design & Setup",
                    "description": "Initial design and DB setup",
                    "amount_minor": 50000,
                },
                {
                    "title": "Implementation",
                    "description": "Frontend and backend logic",
                    "amount_minor": 100000,
                },
            ],
        },
    )
    assert res.status_code == 201
    data = res.json()
    assert data["title"] == "Build Web App"
    assert data["status"] == "draft"
    assert len(data["milestones"]) == 2
    assert data["milestones"][0]["amount_minor"] == 50000


def test_create_contract_unauthenticated_returns_401(client: TestClient, freelancer_user):
    res = client.post(
        "/api/v1/contracts",
        json={
            "freelancer_email": freelancer_user.email,
            "title": "Unauthenticated Contract",
            "description": "Should fail with 401",
            "milestones": [{"title": "M1", "description": "D1", "amount_minor": 1000}],
        },
    )
    assert res.status_code == 401


def test_create_contract_by_freelancer_returns_403(
    client: TestClient, freelancer_token: str, client_user
):
    res = client.post(
        "/api/v1/contracts",
        headers=auth_header(freelancer_token),
        json={
            "freelancer_email": client_user.email,
            "title": "Freelancer Rogue Contract",
            "description": "Freelancers cannot create contracts",
            "milestones": [{"title": "M1", "description": "D1", "amount_minor": 1000}],
        },
    )
    assert res.status_code == 403


def test_create_contract_nonexistent_freelancer_email_returns_404(
    client: TestClient, client_token: str
):
    res = client.post(
        "/api/v1/contracts",
        headers=auth_header(client_token),
        json={
            "freelancer_email": "nonexistent_freelancer_12345@paywork.dev",
            "title": "Missing Freelancer Contract",
            "description": "Should return 404",
            "milestones": [{"title": "M1", "description": "D1", "amount_minor": 1000}],
        },
    )
    assert res.status_code == 404
    assert res.json()["error"]["code"] == "freelancer_not_found"


def test_get_contract_as_client_and_freelancer_and_arbiter(
    client: TestClient, client_token: str, freelancer_token: str, arbiter_token: str, freelancer_user
):
    contract = client.post(
        "/api/v1/contracts",
        headers=auth_header(client_token),
        json={
            "freelancer_email": freelancer_user.email,
            "title": "Viewable Contract",
            "description": "Test viewing permissions",
            "milestones": [{"title": "M1", "description": "D1", "amount_minor": 10000}],
        },
    ).json()
    contract_id = contract["id"]

    # Client view
    res_c = client.get(f"/api/v1/contracts/{contract_id}", headers=auth_header(client_token))
    assert res_c.status_code == 200

    # Freelancer view
    res_f = client.get(f"/api/v1/contracts/{contract_id}", headers=auth_header(freelancer_token))
    assert res_f.status_code == 200

    # Arbiter view
    res_a = client.get(f"/api/v1/contracts/{contract_id}", headers=auth_header(arbiter_token))
    assert res_a.status_code == 200


def test_get_contract_as_outsider_returns_403(
    client: TestClient, client_token: str, freelancer_user
):
    contract = client.post(
        "/api/v1/contracts",
        headers=auth_header(client_token),
        json={
            "freelancer_email": freelancer_user.email,
            "title": "Private Contract",
            "description": "Third party should get 403",
            "milestones": [{"title": "M1", "description": "D1", "amount_minor": 10000}],
        },
    ).json()

    # Another client trying to view
    other_client_reg = client.post(
        "/api/v1/auth/register",
        json={
            "email": f"other_{uuid.uuid4().hex[:8]}@paywork.dev",
            "password": "Password123!",
            "full_name": "Other Client",
            "role": "client",
        },
    ).json()
    res = client.get(
        f"/api/v1/contracts/{contract['id']}",
        headers=auth_header(other_client_reg["access_token"]),
    )
    assert res.status_code == 403


def test_submit_milestone_lifecycle(
    client: TestClient, client_token: str, freelancer_token: str, freelancer_user
):
    # 1. Create contract
    contract = client.post(
        "/api/v1/contracts",
        headers=auth_header(client_token),
        json={
            "freelancer_email": freelancer_user.email,
            "title": "Lifecycle Contract",
            "description": "Testing milestone submit and approve",
            "milestones": [
                {"title": "M1", "description": "D1", "amount_minor": 50000},
            ],
        },
    ).json()
    contract_id = contract["id"]
    milestone_id = contract["milestones"][0]["id"]

    # Try submit while draft -> 409
    res_draft = client.post(
        f"/api/v1/milestones/{milestone_id}/submit",
        headers=auth_header(freelancer_token),
    )
    assert res_draft.status_code == 409

    # Fund the contract with Idempotency-Key
    fund_res = client.post(
        f"/api/v1/contracts/{contract_id}/fund",
        headers={**auth_header(client_token), "Idempotency-Key": str(uuid.uuid4())},
    )
    assert fund_res.status_code == 201

    # Freelancer submits milestone -> 200
    res_sub = client.post(
        f"/api/v1/milestones/{milestone_id}/submit",
        headers=auth_header(freelancer_token),
    )
    assert res_sub.status_code == 200
    assert res_sub.json()["status"] == "submitted"

    # Unauthorized user tries to approve -> 403
    res_bad_app = client.post(
        f"/api/v1/milestones/{milestone_id}/approve",
        headers=auth_header(freelancer_token),
    )
    assert res_bad_app.status_code == 403

    # Client approves milestone -> 200
    res_app = client.post(
        f"/api/v1/milestones/{milestone_id}/approve",
        headers=auth_header(client_token),
    )
    assert res_app.status_code == 200
    assert res_app.json()["status"] == "approved"
