import concurrent.futures
import uuid
from decimal import Decimal
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.src.contracts.models import Milestone, MilestoneStatus
from app.src.escrow import utils as escrow_utils
from app.src.escrow.models import LedgerAccount, LedgerEntry
from app.src.escrow.services import release_milestone
from app.tests.conftest import auth_header, engine


def test_hard_problem_1_funding_same_key_twice_one_pair_ledger_rows(
    client: TestClient, client_token: str, freelancer_user, db_session: Session
):
    """Hard Problem Test 1: Funding with the same key twice -> one pair of ledger rows."""
    contract = client.post(
        "/api/v1/contracts",
        headers=auth_header(client_token),
        json={
            "freelancer_email": freelancer_user.email,
            "title": "Idempotent Funding Contract",
            "description": "Double-click test",
            "milestones": [
                {"title": "M1", "description": "D1", "amount_minor": 150000},
            ],
        },
    ).json()
    contract_id = uuid.UUID(contract["id"])
    key = f"key-{uuid.uuid4()}"

    # First call -> 201 Created
    res1 = client.post(
        f"/api/v1/contracts/{contract_id}/fund",
        headers={**auth_header(client_token), "Idempotency-Key": key},
    )
    assert res1.status_code == 201
    assert res1.json()["status"] == "active"
    assert Decimal(str(res1.json()["funded_amount"])) == Decimal("150000")

    # Second call (replay) -> 200 OK with same payload
    res2 = client.post(
        f"/api/v1/contracts/{contract_id}/fund",
        headers={**auth_header(client_token), "Idempotency-Key": key},
    )
    assert res2.status_code == 200
    assert res2.json()["contract_id"] == str(contract_id)

    # Assert exactly ONE pair of ledger rows (2 rows total) were written
    entries = escrow_utils.list_entries_for_contract(db_session, contract_id)
    assert len(entries) == 2

    client_row = [e for e in entries if e.account == LedgerAccount.CLIENT][0]
    escrow_row = [e for e in entries if e.account == LedgerAccount.ESCROW][0]
    assert client_row.amount == Decimal("-150000")
    assert escrow_row.amount == Decimal("150000")
    assert sum((e.amount for e in entries), Decimal("0")) == Decimal("0")


def test_hard_problem_2_ledger_rows_always_sum_to_zero_after_release(
    client: TestClient, client_token: str, freelancer_token: str, freelancer_user, db_session: Session
):
    """Hard Problem Test 2: After any release, the contract's ledger rows sum to zero."""
    contract = client.post(
        "/api/v1/contracts",
        headers=auth_header(client_token),
        json={
            "freelancer_email": freelancer_user.email,
            "title": "Zero Sum Contract",
            "description": "Double-entry accounting invariant test",
            "milestones": [
                {"title": "M1", "description": "D1", "amount_minor": 60000},
                {"title": "M2", "description": "D2", "amount_minor": 40000},
            ],
        },
    ).json()
    contract_id = uuid.UUID(contract["id"])
    m1_id = contract["milestones"][0]["id"]

    # Fund contract
    client.post(
        f"/api/v1/contracts/{contract_id}/fund",
        headers={**auth_header(client_token), "Idempotency-Key": str(uuid.uuid4())},
    )

    # Freelancer submits and client approves milestone 1
    client.post(f"/api/v1/milestones/{m1_id}/submit", headers=auth_header(freelancer_token))
    client.post(f"/api/v1/milestones/{m1_id}/approve", headers=auth_header(client_token))

    # Invariant: Every ledger row for this contract must sum to zero
    entries = escrow_utils.list_entries_for_contract(db_session, contract_id)
    assert len(entries) == 4  # 2 for funding (client, escrow) + 2 for release (escrow, freelancer)
    total_sum = sum((e.amount for e in entries), Decimal("0"))
    assert total_sum == Decimal("0")

    # Balances: escrow holds 40000, freelancer holds 60000, client -100000
    escrow_bal = escrow_utils.get_balance(db_session, contract_id, LedgerAccount.ESCROW)
    freelancer_bal = escrow_utils.get_balance(db_session, contract_id, LedgerAccount.FREELANCER)
    client_bal = escrow_utils.get_balance(db_session, contract_id, LedgerAccount.CLIENT)
    assert escrow_bal == Decimal("40000")
    assert freelancer_bal == Decimal("60000")
    assert client_bal == Decimal("-100000")


def test_hard_problem_3_release_above_escrow_balance_returns_409(
    client: TestClient, client_token: str, freelancer_token: str, freelancer_user, db_session: Session
):
    """Hard Problem Test 3: Release above the escrow balance -> 409."""
    contract = client.post(
        "/api/v1/contracts",
        headers=auth_header(client_token),
        json={
            "freelancer_email": freelancer_user.email,
            "title": "Insufficient Escrow Contract",
            "description": "Attempt to release more than escrow holds",
            "milestones": [
                {"title": "M1", "description": "D1", "amount_minor": 100000},
            ],
        },
    ).json()
    contract_id = uuid.UUID(contract["id"])
    milestone_id = uuid.UUID(contract["milestones"][0]["id"])

    # Attempt release directly or via service when escrow has 0 funds
    milestone = db_session.get(Milestone, milestone_id)
    assert milestone is not None

    import pytest
    from app.core.errors import ConflictError

    with pytest.raises(ConflictError) as exc_info:
        release_milestone(db_session, milestone)

    assert exc_info.value.status_code == 409
    assert exc_info.value.code == "insufficient_escrow_balance"


def test_hard_problem_4_two_simultaneous_approvals_exactly_one_release(
    client: TestClient, client_token: str, freelancer_token: str, freelancer_user, db_session: Session
):
    """Hard Problem Test 4: Two approvals of the same milestone at the same time -> exactly one release."""
    contract = client.post(
        "/api/v1/contracts",
        headers=auth_header(client_token),
        json={
            "freelancer_email": freelancer_user.email,
            "title": "Race Condition Contract",
            "description": "Concurrent approvals test",
            "milestones": [
                {"title": "M1", "description": "D1", "amount_minor": 50000},
            ],
        },
    ).json()
    contract_id = uuid.UUID(contract["id"])
    milestone_id = contract["milestones"][0]["id"]

    # Fund & submit
    client.post(
        f"/api/v1/contracts/{contract_id}/fund",
        headers={**auth_header(client_token), "Idempotency-Key": str(uuid.uuid4())},
    )
    client.post(f"/api/v1/milestones/{milestone_id}/submit", headers=auth_header(freelancer_token))

    # Approve concurrently using two separate clients
    def _approve():
        with TestClient(client.app) as c:
            return c.post(
                f"/api/v1/milestones/{milestone_id}/approve",
                headers=auth_header(client_token),
            )

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        f1 = executor.submit(_approve)
        f2 = executor.submit(_approve)
        r1 = f1.result()
        r2 = f2.result()

    statuses = sorted([r1.status_code, r2.status_code])
    # Exactly one must succeed with 200, the other rejected with 409
    assert statuses == [200, 409]

    # Exactly one release written (total 4 ledger rows: 2 fund + 2 release)
    entries = escrow_utils.list_entries_for_contract(db_session, contract_id)
    release_entries = [e for e in entries if e.account == LedgerAccount.FREELANCER]
    assert len(release_entries) == 1
    assert release_entries[0].amount == Decimal("50000")


def test_hard_problem_5_arbiter_60_40_split_produces_two_credit_rows(
    client: TestClient, client_token: str, freelancer_token: str, arbiter_token: str, freelancer_user, db_session: Session
):
    """Hard Problem Test 5: Arbiter 60/40 resolution produces exactly two credit rows that sum to milestone amount."""
    contract = client.post(
        "/api/v1/contracts",
        headers=auth_header(client_token),
        json={
            "freelancer_email": freelancer_user.email,
            "title": "Split Resolution Contract",
            "description": "Dispute split test",
            "milestones": [
                {"title": "M1", "description": "D1", "amount_minor": 100000},
            ],
        },
    ).json()
    contract_id = uuid.UUID(contract["id"])
    milestone_id = contract["milestones"][0]["id"]

    # Fund & submit
    client.post(
        f"/api/v1/contracts/{contract_id}/fund",
        headers={**auth_header(client_token), "Idempotency-Key": str(uuid.uuid4())},
    )
    client.post(f"/api/v1/milestones/{milestone_id}/submit", headers=auth_header(freelancer_token))

    # Open dispute on milestone
    dispute = client.post(
        "/api/v1/disputes",
        headers=auth_header(client_token),
        json={"contract_id": str(contract_id), "milestone_id": milestone_id},
    ).json()
    dispute_id = dispute["id"]

    # Arbiter resolves 60/40 (60% to freelancer, 40% refund to client)
    res = client.post(
        f"/api/v1/disputes/{dispute_id}/resolve",
        headers=auth_header(arbiter_token),
        json={"freelancer_percent": 60, "note": "Fair split ruling"},
    )
    assert res.status_code == 200

    # Query ledger rows created for this contract
    entries = escrow_utils.list_entries_for_contract(db_session, contract_id)
    # Total rows: 2 from funding (client -100k, escrow +100k)
    # + 3 from split (escrow -100k, freelancer +60k, client +40k)
    assert len(entries) == 5

    # Check credit rows from resolution
    freelancer_credit = [e for e in entries if e.account == LedgerAccount.FREELANCER][-1]
    client_credit = [e for e in entries if e.account == LedgerAccount.CLIENT and e.amount > 0][-1]
    assert freelancer_credit.amount == Decimal("60000")
    assert client_credit.amount == Decimal("40000")
    assert freelancer_credit.amount + client_credit.amount == Decimal("100000")

    # The entire ledger still sums to zero
    assert sum((e.amount for e in entries), Decimal("0")) == Decimal("0")


def test_statement_endpoint_and_redis_caching(
    client: TestClient, client_token: str, arbiter_token: str, freelancer_user
):
    contract = client.post(
        "/api/v1/contracts",
        headers=auth_header(client_token),
        json={
            "freelancer_email": freelancer_user.email,
            "title": "Statement Test Contract",
            "description": "Verify statement and caching",
            "milestones": [
                {"title": "M1", "description": "D1", "amount_minor": 80000},
            ],
        },
    ).json()
    contract_id = contract["id"]

    # Fund contract
    client.post(
        f"/api/v1/contracts/{contract_id}/fund",
        headers={**auth_header(client_token), "Idempotency-Key": str(uuid.uuid4())},
    )

    # First read (caches in Redis)
    stmt1 = client.get(
        f"/api/v1/contracts/{contract_id}/statement?limit=10&offset=0",
        headers=auth_header(client_token),
    )
    assert stmt1.status_code == 200
    data1 = stmt1.json()
    assert Decimal(str(data1["escrow_balance"])) == Decimal("80000")
    assert len(data1["entries"]) == 2

    # Second read (hits Redis cache)
    stmt2 = client.get(
        f"/api/v1/contracts/{contract_id}/statement?limit=10&offset=0",
        headers=auth_header(arbiter_token),
    )
    assert stmt2.status_code == 200
    assert stmt2.json() == data1
