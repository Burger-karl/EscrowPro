import uuid
from typing import Annotated

from fastapi import APIRouter, Header, Request, Response, status

from app.core.dependencies import CurrentUser, DbSession
from app.src.payments import services
from app.src.payments.schemas import InitiateFundingOut

router = APIRouter(tags=["payments"])


@router.post(
    "/contracts/{contract_id}/fund",
    response_model=InitiateFundingOut,
    summary="Fund contract (client)",
)
async def fund_contract(
    contract_id: uuid.UUID,
    session: DbSession,
    user: CurrentUser,
    response: Response,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
) -> InitiateFundingOut:
    result, is_replay = services.initiate_funding(session, user, contract_id, idempotency_key)
    response.status_code = status.HTTP_200_OK if is_replay else status.HTTP_201_CREATED
    return result


@router.post("/webhooks/payment", summary="Paystack webhook (Paystack only — not user-callable)")
async def payment_webhook(
    request: Request,
    session: DbSession,
    x_paystack_signature: Annotated[str, Header(alias="X-Paystack-Signature")] = "",
) -> dict:
    raw_body = await request.body()
    services.handle_webhook(session, raw_body, x_paystack_signature)
    return {"status": "ok"}