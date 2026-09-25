import hashlib
import hmac
import json
import uuid
from decimal import Decimal
from fastapi.testclient import TestClient
from sqlmodel import Session

from app.core.config import settings
from app.src.contracts.models import Contract, ContractStatus
from app.src.escrow import utils as escrow_utils
from app.src.escrow.models import LedgerAccount
from app.tests.conftest import auth_header


def _make_signature(raw_body: bytes) -> str:
    return hmac.new(
        settings.WEBHOOK_SECRET.encode("utf-8"), raw_body, hashlib.sha256
    ).hexdigest()


def test_webhook_valid_signature_funds_contract(
    client: TestClient, client_token: str, freelancer_user, db_session: Session
):
    # 1. Create a draft contract with milestones
    contract = client.post(
        "/api/v1/contracts",
        headers=auth_header(client_token),
        json={
            "freelancer_email": freelancer_user.email,
            "title": "Webhook Funding Contract",
            "description": "Provider webhook test",
            "milestones": [
                {"title": "M1", "description": "D1", "amount_minor": 120000},
            ],
        },
    ).json()
    contract_id = uuid.UUID(contract["id"])
    assert contract["status"] == "draft"

    # 2. Simulate signed webhook arrival from payment provider
    event_id = f"evt_{uuid.uuid4().hex[:12]}"
    payload = {
        "event_id": event_id,
        "type": "payment.succeeded",
        "reference": str(contract_id),
        "amount": 120000,
        "currency": "NGN",
        "paid_at": "2026-09-25T12:00:00Z",
    }
    raw_body = json.dumps(payload).encode("utf-8")
    sig = _make_signature(raw_body)

    res = client.post(
        "/api/v1/webhooks/payment",
        content=raw_body,
        headers={"X-Signature": sig, "Content-Type": "application/json"},
    )
    assert res.status_code == 200

    # 3. Assert contract status changed to ACTIVE and ledger entries written
    updated_contract = db_session.get(Contract, contract_id)
    db_session.refresh(updated_contract)
    assert updated_contract.status == ContractStatus.ACTIVE

    entries = escrow_utils.list_entries_for_contract(db_session, contract_id)
    assert len(entries) == 2
    escrow_bal = escrow_utils.get_balance(db_session, contract_id, LedgerAccount.ESCROW)
    client_bal = escrow_utils.get_balance(db_session, contract_id, LedgerAccount.CLIENT)
    assert escrow_bal == Decimal("120000")
    assert client_bal == Decimal("-120000")


def test_webhook_duplicate_event_id_idempotent(
    client: TestClient, client_token: str, freelancer_user, db_session: Session
):
    contract = client.post(
        "/api/v1/contracts",
        headers=auth_header(client_token),
        json={
            "freelancer_email": freelancer_user.email,
            "title": "Idempotent Webhook Contract",
            "description": "Duplicate delivery test",
            "milestones": [{"title": "M1", "description": "D1", "amount_minor": 50000}],
        },
    ).json()
    contract_id = uuid.UUID(contract["id"])

    event_id = f"evt_dup_{uuid.uuid4().hex[:12]}"
    payload = {
        "event_id": event_id,
        "type": "payment.succeeded",
        "reference": str(contract_id),
        "amount": 50000,
        "currency": "NGN",
        "paid_at": "2026-09-25T12:00:00Z",
    }
    raw_body = json.dumps(payload).encode("utf-8")
    sig = _make_signature(raw_body)

    # First delivery
    res1 = client.post(
        "/api/v1/webhooks/payment",
        content=raw_body,
        headers={"X-Signature": sig, "Content-Type": "application/json"},
    )
    assert res1.status_code == 200

    # Second delivery (identical event_id) -> 200 and no new rows
    res2 = client.post(
        "/api/v1/webhooks/payment",
        content=raw_body,
        headers={"X-Signature": sig, "Content-Type": "application/json"},
    )
    assert res2.status_code == 200

    entries = escrow_utils.list_entries_for_contract(db_session, contract_id)
    assert len(entries) == 2


def test_webhook_bad_signature_returns_401(client: TestClient):
    payload = {
        "event_id": "evt_fake",
        "type": "payment.succeeded",
        "reference": str(uuid.uuid4()),
        "amount": 50000,
    }
    raw_body = json.dumps(payload).encode("utf-8")

    res = client.post(
        "/api/v1/webhooks/payment",
        content=raw_body,
        headers={"X-Signature": "invalid_hex_signature", "Content-Type": "application/json"},
    )
    assert res.status_code == 401


def test_webhook_unknown_reference_returns_200_orphan(client: TestClient):
    event_id = f"evt_orphan_{uuid.uuid4().hex[:8]}"
    payload = {
        "event_id": event_id,
        "type": "payment.succeeded",
        "reference": str(uuid.uuid4()),  # Unknown reference
        "amount": 50000,
    }
    raw_body = json.dumps(payload).encode("utf-8")
    sig = _make_signature(raw_body)

    res = client.post(
        "/api/v1/webhooks/payment",
        content=raw_body,
        headers={"X-Signature": sig, "Content-Type": "application/json"},
    )
    assert res.status_code == 200
