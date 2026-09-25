import uuid
from typing import Annotated

from fastapi import APIRouter, Header, Request, Response, status

from app.core.dependencies import CurrentUser, DbSession
from app.src.payments import services
from app.src.payments.schemas import FundContractOut

router = APIRouter(tags=["Payments"])


@router.post(
    "/contracts/{contract_id}/fund",
    response_model=FundContractOut,
    summary="[Role: Client] Fund contract escrow",
    description="Locks client funds into contract escrow using immutable double-entry ledger guarantee. Requires 'Idempotency-Key' header; replays return saved 200 OK without re-charging. Accessible by: Contract Client.",
)
async def fund_contract(
    contract_id: uuid.UUID,
    session: DbSession,
    user: CurrentUser,
    response: Response,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
) -> FundContractOut:
    """Funds the contract using double-entry ledger entries.
    201 on success (new key), 200 on replay (seen key), 401 unauthenticated, 403 not contract client, 404 contract not found, 409 already funded.
    """
    result, is_replay = services.fund_contract(session, user, contract_id, idempotency_key)
    response.status_code = status.HTTP_200_OK if is_replay else status.HTTP_201_CREATED
    return result


@router.post(
    "/webhooks/payment",
    summary="[Role: Machine (Signature)] Payment provider webhook",
    description="Processes incoming payment confirmation webhooks from external providers (supports standard Capstone HMAC-SHA256 via 'X-Signature' and Paystack HMAC-SHA512 via 'X-Paystack-Signature'). Automatically detects orphan payments and maintains idempotency via processed_events table. Accessible by: Machine / Payment Provider (Cryptographically Signed).",
)
async def payment_webhook(
    request: Request,
    session: DbSession,
    x_signature: Annotated[str | None, Header(alias="X-Signature")] = None,
    x_paystack_signature: Annotated[str | None, Header(alias="X-Paystack-Signature")] = None,
) -> dict:
    raw_body = await request.body()
    return services.handle_webhook(
        session,
        raw_body,
        x_signature=x_signature,
        x_paystack_signature=x_paystack_signature,
    )