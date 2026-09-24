import hashlib
import hmac
import json
import uuid
from decimal import Decimal

from sqlmodel import Session

from app.core.config import settings
from app.core.errors import ConflictError, ForbiddenError, NotFoundError, UnauthorizedError
from app.src.payments.paystack_client import paystack_client
from app.src.accounts.models import User
from app.src.contracts import utils as contracts_utils
from app.src.contracts.models import ContractStatus
from app.src.escrow import services as escrow_services
from app.src.escrow import utils as escrow_utils
from app.src.payments import utils
from app.src.payments.models import PaymentTransaction, PaymentTransactionStatus
from app.src.payments.schemas import InitiateFundingOut


def verify_webhook_signature(raw_body: bytes, signature: str) -> bool:
    """
    Paystack signs webhooks with HMAC-SHA512 over the raw request body,
    using your API secret key — NOT a separate webhook secret (Paystack
    has no such thing, unlike Stripe). Verify the RAW bytes, before any
    JSON parsing — parsing first and re-serializing can change byte-for-byte
    formatting and break the signature check.
    """
    if not signature:
        return False
    expected = hmac.new(
        settings.PAYSTACK_SECRET_KEY.encode("utf-8"), raw_body, hashlib.sha512
    ).hexdigest()
    return hmac.compare_digest(expected, signature)


def initiate_funding(
    session: Session,
    client: User,
    contract_id: uuid.UUID,
    idempotency_key: str,
) -> tuple[InitiateFundingOut, bool]:
    """Returns (response, is_replay) — same idempotency-replay shape as before."""
    endpoint = f"/contracts/{contract_id}/fund"

    existing = escrow_utils.get_idempotency_key(session, idempotency_key)
    if existing is not None:
        if existing.endpoint != endpoint:
            raise ConflictError(
                "this idempotency key was already used for a different request",
                code="idempotency_key_reused",
            )
        return InitiateFundingOut.model_validate(json.loads(existing.response_json)), True

    contract = contracts_utils.get_contract_by_id(session, contract_id)
    if contract is None:
        raise NotFoundError("contract not found", code="contract_not_found")

    if contract.client_id != client.id:
        raise ForbiddenError(
            "only the contract's client can fund it", code="not_contract_client"
        )

    if contract.status != ContractStatus.DRAFT:
        raise ConflictError(
            f"contract cannot be funded from status '{contract.status.value}'",
            code="invalid_contract_state",
        )

    milestones = contracts_utils.list_milestones_for_contract(session, contract.id)
    total = sum((Decimal(m.amount_minor) for m in milestones), Decimal("0"))
    if total <= 0:
        raise ConflictError("contract has no milestones to fund", code="nothing_to_fund")

    reference = f"paywork-{uuid.uuid4()}"

    # Confirmed against the installed paystackease version: PayStackBase()
    # exposes sub-clients as attributes — paystack_client.transactions here.
    paystack_response = paystack_client.transactions.initialize(
        email=client.email,
        amount=int(total),  # smallest currency unit, matches your amount_minor scale
        currency="NGN",
        reference=reference,
        callback_url=settings.PAYSTACK_CALLBACK_URL,
        metadata={"contract_id": str(contract_id)},
    )

    utils.save_transaction(
        session,
        PaymentTransaction(
            contract_id=contract.id,
            reference=reference,
            amount_minor=int(total),
            status=PaymentTransactionStatus.PENDING,
        ),
    )

    response = InitiateFundingOut(
        contract_id=contract.id,
        reference=reference,
        checkout_url=paystack_response.checkout_url,
        amount=total,
    )

    escrow_utils.save_idempotency_key(
        session,
        key=idempotency_key,
        endpoint=endpoint,
        response_json=response.model_dump_json(),
        status_code=201,
    )

    session.commit()
    return response, False


def handle_webhook(session: Session, raw_body: bytes, signature: str) -> None:
    if not verify_webhook_signature(raw_body, signature):
        raise UnauthorizedError("invalid webhook signature", code="invalid_signature")

    payload = json.loads(raw_body)
    event_type = payload.get("event")
    data = payload.get("data", {})
    reference = data.get("reference")

    if not reference:
        # Malformed/irrelevant event — acknowledge with 200 so Paystack
        # doesn't retry something we'll never be able to process anyway.
        return

    event_id = f"{event_type}:{reference}"
    if utils.get_processed_event(session, event_id) is not None:
        return  # already handled — Paystack redelivered

    if event_type == "charge.success":
        transaction = utils.get_transaction_by_reference(session, reference)
        if transaction is None:
            utils.save_processed_event(session, event_id, reference)
            session.commit()
            return

        # Defense in depth: re-verify server-to-server with Paystack rather
        # than trusting the webhook body's amount/status alone.
        verify_response = paystack_client.transactions.verify_transaction(reference)
        verified_amount = verify_response.data.get("amount")
        verified_status = verify_response.data.get("status")

        if verified_status == "success" and verified_amount == transaction.amount_minor:
            escrow_services.confirm_funding(session, transaction.contract_id, Decimal(transaction.amount_minor))
            utils.mark_transaction_status(session, transaction, PaymentTransactionStatus.SUCCESS)
        else:
            utils.mark_transaction_status(session, transaction, PaymentTransactionStatus.FAILED)

    # transfer.success / transfer.failed handling for payouts goes here
    # once payouts.mark_payout_sent calls the Transfers API for real.

    utils.save_processed_event(session, event_id, reference)
    session.commit()