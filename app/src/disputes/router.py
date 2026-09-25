import uuid

from fastapi import APIRouter, BackgroundTasks, status
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import StreamingResponse

from app.core.dependencies import CurrentUser, DbSession
from app.platform.events.broadcaster import broadcaster
from app.platform.tasks.background import notify_dispute_opened, notify_dispute_resolved
from app.src.accounts import utils as accounts_utils
from app.src.contracts import utils as contracts_utils
from app.src.disputes import services
from app.src.disputes.schemas import (
    DisputeOpenIn,
    DisputeOut,
    DisputeResolveIn,
    MessageIn,
    MessageOut,
)

router = APIRouter(tags=["Disputes"])


@router.post(
    "/disputes",
    response_model=DisputeOut,
    status_code=status.HTTP_201_CREATED,
    summary="[Role: Client, Freelancer] Open dispute",
    description="Raises a formal dispute on a submitted milestone or active contract, freezing milestone actions and notifying both parties. Accessible by: Client (contract owner), Freelancer (assigned).",
)
async def open_dispute(
    data: DisputeOpenIn,
    session: DbSession,
    user: CurrentUser,
    background_tasks: BackgroundTasks,
) -> DisputeOut:
    """201 on success, 403 if not a party, 404 if the milestone doesn't exist, 409 if one's already open on this contract or the target isn't in a disputable state."""
    dispute = services.open_dispute(session, user, data)
    contract = contracts_utils.get_contract_by_id(session, dispute.contract_id)
    if contract:
        client_user = accounts_utils.get_user_by_id(session, contract.client_id)
        freelancer_user = accounts_utils.get_user_by_id(session, contract.freelancer_id)
        if client_user and freelancer_user:
            background_tasks.add_task(
                notify_dispute_opened, client_user.email, freelancer_user.email, contract.title
            )
    return DisputeOut.model_validate(dispute)


@router.post(
    "/disputes/{dispute_id}/messages",
    response_model=MessageOut,
    status_code=status.HTTP_201_CREATED,
    summary="[Role: Client, Freelancer, Arbiter, Admin] Post dispute message",
    description="Publishes a message to the dispute thread stored in Firestore and broadcasts it over SSE. Accessible by: Client (contract owner), Freelancer (assigned), Arbiter, Admin.",
)
async def post_message(
    dispute_id: uuid.UUID,
    data: MessageIn,
    session: DbSession,
    user: CurrentUser,
) -> MessageOut:
    """201 on success, 403 if not a party or arbiter, 404 if the dispute doesn't exist, 409 if the dispute is already resolved, 503 if firestore is unreachable."""
    return services.post_message(session, user, dispute_id, data)


@router.post(
    "/disputes/{dispute_id}/resolve",
    response_model=DisputeOut,
    summary="[Role: Arbiter, Admin] Resolve dispute",
    description="Applies a percentage-based split ruling between client refund and freelancer payout, executing double-entry ledger settlement and unfreezing/completing the contract. Accessible by: Arbiter, Admin.",
)
async def resolve_dispute(
    dispute_id: uuid.UUID,
    data: DisputeResolveIn,
    session: DbSession,
    user: CurrentUser,
    background_tasks: BackgroundTasks,
) -> DisputeOut:
    """200 on success, 403 if not the arbiter, 404 if not found, 422 if the split
    is invalid, 409 if already resolved or nothing left to settle."""
    dispute = services.resolve_dispute(session, user, dispute_id, data)
    contract = contracts_utils.get_contract_by_id(session, dispute.contract_id)
    if contract:
        client_user = accounts_utils.get_user_by_id(session, contract.client_id)
        freelancer_user = accounts_utils.get_user_by_id(session, contract.freelancer_id)
        if client_user and freelancer_user:
            background_tasks.add_task(
                notify_dispute_resolved, client_user.email, freelancer_user.email, contract.title
            )
    return DisputeOut.model_validate(dispute)


@router.get(
    "/disputes/{dispute_id}/stream",
    summary="[Role: Client, Freelancer, Arbiter, Admin] Stream dispute updates (SSE)",
    description="Streams real-time Server-Sent Events (SSE) for messages and dispute resolution status. Accessible by: Client (contract owner), Freelancer (assigned), Arbiter, Admin.",
)
async def stream_dispute(
    dispute_id: uuid.UUID,
    session: DbSession,
    user: CurrentUser,
) -> StreamingResponse:
    """Server-Sent Events. 200 (text/event-stream), 401 no/invalid token, 403 not a party or the arbiter, 404 dispute not found."""
    await run_in_threadpool(services.get_dispute_for_viewer, session, user, dispute_id)

    # A stream can stay open for hours. Give the database connection back now instead of holding it for the whole stream.
    await run_in_threadpool(session.close)

    return StreamingResponse(
        broadcaster.event_stream(services.dispute_topic(dispute_id)),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
