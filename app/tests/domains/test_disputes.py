import uuid
from fastapi.testclient import TestClient

from app.tests.conftest import auth_header


def test_open_milestone_dispute_success(
    client: TestClient, client_token: str, freelancer_token: str, freelancer_user
):
    contract = client.post(
        "/api/v1/contracts",
        headers=auth_header(client_token),
        json={
            "freelancer_email": freelancer_user.email,
            "title": "Dispute Contract",
            "description": "Milestone dispute test",
            "milestones": [
                {"title": "M1", "description": "D1", "amount_minor": 50000},
            ],
        },
    ).json()
    contract_id = contract["id"]
    milestone_id = contract["milestones"][0]["id"]

    # Fund & submit
    client.post(
        f"/api/v1/contracts/{contract_id}/fund",
        headers={**auth_header(client_token), "Idempotency-Key": str(uuid.uuid4())},
    )
    client.post(f"/api/v1/milestones/{milestone_id}/submit", headers=auth_header(freelancer_token))

    # Open dispute on milestone
    res = client.post(
        "/api/v1/disputes",
        headers=auth_header(client_token),
        json={"contract_id": contract_id, "milestone_id": milestone_id},
    )
    assert res.status_code == 201
    data = res.json()
    assert data["status"] == "open"
    assert data["milestone_id"] == milestone_id

    # Verify client cannot approve a disputed milestone -> 409
    res_app = client.post(
        f"/api/v1/milestones/{milestone_id}/approve",
        headers=auth_header(client_token),
    )
    assert res_app.status_code == 409


def test_open_duplicate_dispute_returns_409(
    client: TestClient, client_token: str, freelancer_token: str, freelancer_user
):
    contract = client.post(
        "/api/v1/contracts",
        headers=auth_header(client_token),
        json={
            "freelancer_email": freelancer_user.email,
            "title": "Dup Dispute Contract",
            "description": "Only one dispute at a time",
            "milestones": [
                {"title": "M1", "description": "D1", "amount_minor": 50000},
            ],
        },
    ).json()
    contract_id = contract["id"]
    milestone_id = contract["milestones"][0]["id"]

    client.post(
        f"/api/v1/contracts/{contract_id}/fund",
        headers={**auth_header(client_token), "Idempotency-Key": str(uuid.uuid4())},
    )
    client.post(f"/api/v1/milestones/{milestone_id}/submit", headers=auth_header(freelancer_token))

    # First dispute
    res1 = client.post(
        "/api/v1/disputes",
        headers=auth_header(client_token),
        json={"contract_id": contract_id, "milestone_id": milestone_id},
    )
    assert res1.status_code == 201

    # Second dispute attempt -> 409
    res2 = client.post(
        "/api/v1/disputes",
        headers=auth_header(freelancer_token),
        json={"contract_id": contract_id, "milestone_id": milestone_id},
    )
    assert res2.status_code == 409
    assert res2.json()["error"]["code"] == "dispute_already_open"


def test_dispute_messages_permissions(
    client: TestClient, client_token: str, freelancer_token: str, arbiter_token: str, freelancer_user
):
    contract = client.post(
        "/api/v1/contracts",
        headers=auth_header(client_token),
        json={
            "freelancer_email": freelancer_user.email,
            "title": "Message Thread Contract",
            "description": "Testing message posting",
            "milestones": [{"title": "M1", "description": "D1", "amount_minor": 40000}],
        },
    ).json()
    contract_id = contract["id"]
    milestone_id = contract["milestones"][0]["id"]

    client.post(
        f"/api/v1/contracts/{contract_id}/fund",
        headers={**auth_header(client_token), "Idempotency-Key": str(uuid.uuid4())},
    )
    client.post(f"/api/v1/milestones/{milestone_id}/submit", headers=auth_header(freelancer_token))

    dispute = client.post(
        "/api/v1/disputes",
        headers=auth_header(client_token),
        json={"contract_id": contract_id, "milestone_id": milestone_id},
    ).json()
    dispute_id = dispute["id"]

    # Client posts message -> 201
    res_c = client.post(
        f"/api/v1/disputes/{dispute_id}/messages",
        headers=auth_header(client_token),
        json={"body": "Work is not as agreed."},
    )
    assert res_c.status_code == 201
    assert res_c.json()["author_role"] == "client"

    # Freelancer posts message -> 201
    res_f = client.post(
        f"/api/v1/disputes/{dispute_id}/messages",
        headers=auth_header(freelancer_token),
        json={"body": "I followed the specification exactly."},
    )
    assert res_f.status_code == 201
    assert res_f.json()["author_role"] == "freelancer"

    # Arbiter posts message -> 201
    res_a = client.post(
        f"/api/v1/disputes/{dispute_id}/messages",
        headers=auth_header(arbiter_token),
        json={"body": "Reviewing evidence now."},
    )
    assert res_a.status_code == 201
    assert res_a.json()["author_role"] == "arbiter"


def test_resolve_dispute_permissions_and_lifecycle(
    client: TestClient, client_token: str, freelancer_token: str, arbiter_token: str, freelancer_user
):
    contract = client.post(
        "/api/v1/contracts",
        headers=auth_header(client_token),
        json={
            "freelancer_email": freelancer_user.email,
            "title": "Resolve Life Contract",
            "description": "Resolution lifecycle",
            "milestones": [{"title": "M1", "description": "D1", "amount_minor": 50000}],
        },
    ).json()
    contract_id = contract["id"]
    milestone_id = contract["milestones"][0]["id"]

    client.post(
        f"/api/v1/contracts/{contract_id}/fund",
        headers={**auth_header(client_token), "Idempotency-Key": str(uuid.uuid4())},
    )
    client.post(f"/api/v1/milestones/{milestone_id}/submit", headers=auth_header(freelancer_token))

    dispute = client.post(
        "/api/v1/disputes",
        headers=auth_header(client_token),
        json={"contract_id": contract_id, "milestone_id": milestone_id},
    ).json()
    dispute_id = dispute["id"]

    # Non-arbiter cannot resolve -> 403
    res_rogue = client.post(
        f"/api/v1/disputes/{dispute_id}/resolve",
        headers=auth_header(client_token),
        json={"freelancer_percent": 50},
    )
    assert res_rogue.status_code == 403

    # Arbiter resolves -> 200
    res_arb = client.post(
        f"/api/v1/disputes/{dispute_id}/resolve",
        headers=auth_header(arbiter_token),
        json={"freelancer_percent": 70, "note": "70% to freelancer"},
    )
    assert res_arb.status_code == 200
    assert res_arb.json()["status"] == "resolved"

    # Resolving already resolved dispute -> 409
    res_again = client.post(
        f"/api/v1/disputes/{dispute_id}/resolve",
        headers=auth_header(arbiter_token),
        json={"freelancer_percent": 50},
    )
    assert res_again.status_code == 409
