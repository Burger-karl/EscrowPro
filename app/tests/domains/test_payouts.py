import uuid
from decimal import Decimal
from fastapi.testclient import TestClient
from sqlmodel import Session

from app.src.escrow import utils as escrow_utils
from app.src.escrow.models import LedgerAccount
from app.tests.conftest import auth_header


def test_payout_request_and_mark_sent_flow(
    client: TestClient,
    client_token: str,
    freelancer_token: str,
    finance_token: str,
    freelancer_user,
    db_session: Session,
):
    # 1. Setup funded contract with 1 approved milestone
    contract = client.post(
        "/api/v1/contracts",
        headers=auth_header(client_token),
        json={
            "freelancer_email": freelancer_user.email,
            "title": "Payout Test Contract",
            "description": "Milestone payout flow",
            "milestones": [
                {"title": "M1", "description": "D1", "amount_minor": 75000},
            ],
        },
    ).json()
    contract_id = uuid.UUID(contract["id"])
    milestone_id = contract["milestones"][0]["id"]

    # Fund & submit & approve
    client.post(
        f"/api/v1/contracts/{contract_id}/fund",
        headers={**auth_header(client_token), "Idempotency-Key": str(uuid.uuid4())},
    )
    client.post(f"/api/v1/milestones/{milestone_id}/submit", headers=auth_header(freelancer_token))
    client.post(f"/api/v1/milestones/{milestone_id}/approve", headers=auth_header(client_token))

    # 2. Non-freelancer cannot request payout -> 403
    res_bad = client.post(
        "/api/v1/payouts",
        headers=auth_header(client_token),
        json={"milestone_id": milestone_id},
    )
    assert res_bad.status_code == 403

    # 3. Freelancer requests payout -> 201
    res_payout = client.post(
        "/api/v1/payouts",
        headers=auth_header(freelancer_token),
        json={"milestone_id": milestone_id},
    )
    assert res_payout.status_code == 201
    payout_data = res_payout.json()
    assert payout_data["status"] == "pending"
    assert payout_data["amount_minor"] == 75000
    payout_id = payout_data["id"]

    # 4. Duplicate payout request on same milestone -> 409
    res_dup = client.post(
        "/api/v1/payouts",
        headers=auth_header(freelancer_token),
        json={"milestone_id": milestone_id},
    )
    assert res_dup.status_code == 409

    # 5. Non-finance cannot mark payout sent -> 403
    res_rogue_sent = client.post(
        f"/api/v1/payouts/{payout_id}/mark-sent",
        headers=auth_header(freelancer_token),
    )
    assert res_rogue_sent.status_code == 403

    # 6. Finance marks payout sent -> 200
    res_sent = client.post(
        f"/api/v1/payouts/{payout_id}/mark-sent",
        headers=auth_header(finance_token),
    )
    assert res_sent.status_code == 200
    assert res_sent.json()["status"] == "sent"

    # Verify ledger entries: freelancer debited 75000, payout credited 75000
    freelancer_bal = escrow_utils.get_balance(db_session, contract_id, LedgerAccount.FREELANCER)
    payout_bal = escrow_utils.get_balance(db_session, contract_id, LedgerAccount.PAYOUT)
    assert freelancer_bal == Decimal("0")
    assert payout_bal == Decimal("75000")


def test_admin_can_mark_payout_sent(
    client: TestClient,
    client_token: str,
    freelancer_token: str,
    admin_token: str,
    freelancer_user,
):
    contract = client.post(
        "/api/v1/contracts",
        headers=auth_header(client_token),
        json={
            "freelancer_email": freelancer_user.email,
            "title": "Admin Payout Contract",
            "description": "Admin super access on payouts",
            "milestones": [
                {"title": "M1", "description": "D1", "amount_minor": 30000},
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
    client.post(f"/api/v1/milestones/{milestone_id}/approve", headers=auth_header(client_token))

    payout = client.post(
        "/api/v1/payouts",
        headers=auth_header(freelancer_token),
        json={"milestone_id": milestone_id},
    ).json()

    # Admin marks sent -> 200
    res = client.post(
        f"/api/v1/payouts/{payout['id']}/mark-sent",
        headers=auth_header(admin_token),
    )
    assert res.status_code == 200
    assert res.json()["status"] == "sent"
