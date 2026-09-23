import uuid

from fastapi import APIRouter, status
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import StreamingResponse

from app.core.dependencies import CurrentUser, DbSession
from app.platform.events.broadcaster import broadcaster
from app.src.disputes import services
from app.src.disputes.schemas import (
    DisputeOpenIn,
    DisputeOut,
    DisputeResolveIn,
    MessageIn,
    MessageOut,
)

router = APIRouter(tags=["Disputes"])


@router.post("/disputes", response_model=DisputeOut, status_code=status.HTTP_201_CREATED)
async def open_dispute(
    data: DisputeOpenIn,
    session: DbSession,
    user: CurrentUser,
) -> DisputeOut:
    """201 on success, 403 if not a party, 404 if the milestone doesn't exist, 409 if one's already open on this contract or the target isn't in a disputable state."""
    dispute = services.open_dispute(session, user, data)
    return DisputeOut.model_validate(dispute)


@router.post(
    "/disputes/{dispute_id}/messages", response_model=MessageOut, 
    status_code=status.HTTP_201_CREATED
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
    "/disputes/{dispute_id}/resolve", response_model=DisputeOut 
)
async def resolve_dispute(
    dispute_id: uuid.UUID,
    data: DisputeResolveIn,
    session: DbSession,
    user: CurrentUser,
) -> DisputeOut:
    """200 on success, 403 if not the arbiter, 404 if not found, 422 if the split
    is invalid, 409 if already resolved or nothing left to settle."""
    dispute = services.resolve_dispute(session, user, dispute_id, data)
    return DisputeOut.model_validate(dispute)


@router.get("/disputes/{dispute_id}/stream")
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








