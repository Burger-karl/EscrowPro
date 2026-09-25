import uuid

from fastapi import APIRouter, BackgroundTasks, status

from app.core.dependencies import CurrentUser, DbSession
from app.platform.tasks.background import notify_payout_sent
from app.src.accounts import utils as accounts_utils
from app.src.payouts import services
from app.src.payouts.schemas import PayoutCreateIn, PayoutOut

router = APIRouter(tags=["Payouts"])


@router.post(
    "/payouts",
    response_model=PayoutOut,
    status_code=status.HTTP_201_CREATED,
    summary="[Role: Freelancer] Request milestone payout",
    description="Requests withdrawal of earnings for an approved milestone to the freelancer's registered bank account. Accessible by: Assigned Freelancer.",
)
async def request_payout(
    data: PayoutCreateIn,
    session: DbSession,
    user: CurrentUser,
) -> PayoutOut:
    payout = services.request_payout(session, user, data)
    return PayoutOut.model_validate(payout)


@router.post(
    "/payouts/{payout_id}/mark-sent",
    response_model=PayoutOut,
    summary="[Role: Finance, Admin] Mark payout sent",
    description="Confirms that external bank disbursement has been executed, transitioning payout status to SENT and notifying the freelancer via background email. Accessible by: Finance, Admin.",
)
async def mark_payout_sent(
    payout_id: uuid.UUID,
    session: DbSession,
    user: CurrentUser,
    background_tasks: BackgroundTasks,
) -> PayoutOut:
    payout = services.mark_payout_sent(session, user, payout_id)
    freelancer = accounts_utils.get_user_by_id(session, payout.freelancer_id)
    if freelancer:
        background_tasks.add_task(notify_payout_sent, freelancer.email, payout.amount_minor)
    return PayoutOut.model_validate(payout)