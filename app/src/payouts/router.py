import uuid

from fastapi import APIRouter, status

from app.core.dependencies import CurrentUser, DbSession
from app.src.payouts import services
from app.src.payouts.schemas import PayoutCreateIn, PayoutOut


router = APIRouter(tags=["Payouts"])

@router.post("/payouts", response_model=PayoutOut, status_code=status.HTTP_201_CREATED)
async def request_payout(
    data: PayoutCreateIn,
    session: DbSession,
    user: CurrentUser,
) -> PayoutOut:
    payout = services.request_payout(session, user, data)
    return PayoutOut.model_validate(payout)


@router.post("/payouts/{payout_id}/mark-sent", response_model=PayoutOut)
async def mark_payout_sent(
    payout_id: uuid.UUID,
    session: DbSession,
    user: CurrentUser,
) -> PayoutOut:
    payout = services.mark_payout_sent(session, user, payout_id)
    return PayoutOut.model_validate(payout)