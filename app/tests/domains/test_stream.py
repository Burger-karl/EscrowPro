import asyncio
import uuid
import pytest
from fastapi.testclient import TestClient

from app.platform.events.broadcaster import broadcaster, make_event
from app.src.disputes.services import dispute_topic
from app.tests.conftest import auth_header


def test_stream_unauthenticated_returns_401(client: TestClient):
    res = client.get(f"/api/v1/disputes/{uuid.uuid4()}/stream")
    assert res.status_code == 401


def test_stream_outsider_returns_403(
    client: TestClient, client_token: str, freelancer_token: str, freelancer_user
):
    contract = client.post(
        "/api/v1/contracts",
        headers=auth_header(client_token),
        json={
            "freelancer_email": freelancer_user.email,
            "title": "Stream Auth Contract",
            "description": "Stream security test",
            "milestones": [{"title": "M1", "description": "D1", "amount_minor": 10000}],
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

    # Register an unrelated user
    outsider = client.post(
        "/api/v1/auth/register",
        json={
            "email": f"outsider_{uuid.uuid4().hex[:8]}@paywork.dev",
            "password": "Password123!",
            "full_name": "Outsider",
            "role": "client",
        },
    ).json()

    res = client.get(
        f"/api/v1/disputes/{dispute_id}/stream",
        headers=auth_header(outsider["access_token"]),
    )
    assert res.status_code == 403


@pytest.mark.asyncio
async def test_stream_broadcaster_event_delivery():
    test_id = uuid.uuid4()
    topic = dispute_topic(test_id)

    queue = broadcaster.subscribe(topic)
    try:
        event = make_event("message.created", "msg-123", {"body": "Hello live stream"})
        broadcaster.publish(topic, event)

        received = await asyncio.wait_for(queue.get(), timeout=2.0)
        assert received["type"] == "message.created"
        assert received["id"] == "msg-123"
        assert received["data"]["body"] == "Hello live stream"
    finally:
        broadcaster.unsubscribe(topic, queue)
