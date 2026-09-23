"""Everything that touches firestore for dispute lives in this file."""

import logging
import uuid
from datetime import datetime
from typing import Any

from app.platform.firestore.client import get_firestore_client

logger = logging.getLogger(__name__)

THREADS = "dispute_threads"
MESSAGES = "messages"


def _thread_ref(dispute_id: uuid.UUID):
    return get_firestore_client().collection(THREADS).document(str(dispute_id))


def create_thread(
    dispute_id: uuid.UUID,
    contract_id: uuid.UUID,
    milestone_id: uuid.UUID | None,
    opened_by: uuid.UUID,
    created_at: datetime,
) -> None:
    _thread_ref(dispute_id).set(
        {
            "dispute_id": str(dispute_id),
            "contract_id": str(contract_id),
            "milestone_id": str(milestone_id) if milestone_id else None,
            "scope": "milestone" if milestone_id else "contract",
            "opened_by": str(opened_by),
            "status": "open",
            "created_at": created_at,
        }
    )


def add_message(
        dispute_id: uuid.UUID,
        message: dict[str, Any]
) -> None:
    _thread_ref(dispute_id).collection(MESSAGES).document(str(message["id"])).set(message)


def mark_thread_resolved(dispute_id: uuid.UUID, resolution: dict[str, Any]) -> None:
    _thread_ref(dispute_id).set({"status": "resolved", "resolution": resolution}, merge=True)
