import hashlib
import hmac
import json
import logging
import uuid
from decimal import Decimal

from sqlmodel import Session

from app.core.config import settings
from app.core.errors import ConflictError, ForbiddenError, NotFoundError, UnauthorizedError
from app.src.accounts.models import User, UserRole
from app.src.contracts import utils as contracts_utils
from app.src.contracts.models import ContractStatus
from app.src.escrow import services as escrow_services
from app.src.escrow import utils as escrow_utils
from app.src.escrow.models import LedgerAccount, LedgerEntry
from app.src.payments import utils
from app.src.payments.models import PaymentTransaction, PaymentTransactionStatus
from app.src.payments.paystack_client import paystack_client
from app.src.payments.schemas import FundContractOut, InitiateFundingOut
from app.platform.cache import redis_client

logger = logging.getLogger(__name__)


def verify_standard_webhook_signature(raw_body: bytes, signature: str) -> bool:
    """Capstone specification: HMAC-SHA256 of raw request body using WEBHOOK_SECRET."""
    if not signature:
        return False
    expected = hmac.new(
        settings.WEBHOOK_SECRET.encode("utf-8"), raw_body, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, signature)


def verify_paystack_webhook_signature(raw_body: bytes, signature: str) -> bool:
    """Paystack specification: HMAC-SHA512 of raw request body using PAYSTACK_SECRET_KEY."""
    if not signature:
        return False
    secret = settings.PAYSTACK_SECRET_KEY or ""
    expected = hmac.new(
        secret.encode("utf-8"), raw_body, hashlib.sha512
    ).hexdigest()
    return hmac.compare_digest(expected, signature)


def fund_contract(
    session: Session,
    client: User,
    contract_id: uuid.UUID,
    idempotency_key: str,
    prefer_paystack: bool = False,
) -> tuple[FundContractOut, bool]:
    """Funds the contract and records ledger movement.
    
    Adheres strictly to the Capstone flow (Page 10) & Hard Problem Test 1:
    - Lock contract row (SELECT ... FOR UPDATE)
    - Check contract ownership & draft status
    - Idempotency check: replay returns saved response and writes nothing
    - Write ledger entries (client -X, escrow +X)
    - Activate contract
    - Save idempotency key with 201 response
    """
    endpoint = f"/contracts/{contract_id}/fund"

    # 1. Lock contract row first to prevent race conditions
    contract = escrow_utils.get_contract_for_update(session, contract_id)
    if contract is None:
        raise NotFoundError("contract not found", code="contract_not_found")

    if contract.client_id != client.id and client.role != UserRole.ADMIN:
        raise ForbiddenError(
            "only the contract's client can fund it", code="not_contract_client"
        )

    # 2. Check idempotency key for this endpoint
    existing = escrow_utils.get_idempotency_key(session, idempotency_key)
    if existing is not None:
        if existing.endpoint != endpoint:
            raise ConflictError(
                "this idempotency key was already used for a different request",
                code="idempotency_key_reused",
            )
        return FundContractOut.model_validate(json.loads(existing.response_json)), True

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
    checkout_url = None

    if prefer_paystack and settings.PAYSTACK_SECRET_KEY:
        try:
            paystack_response = paystack_client.transactions.initialize(
                email=client.email,
                amount=int(total),
                currency="NGN",
                reference=reference,
                callback_url=settings.PAYSTACK_CALLBACK_URL,
                metadata={"contract_id": str(contract_id)},
            )
            checkout_url = paystack_response.checkout_url
        except Exception:
            logger.warning("Could not initialize Paystack checkout session; proceeding with direct funding")

    # Record PaymentTransaction
    utils.save_transaction(
        session,
        PaymentTransaction(
            contract_id=contract.id,
            reference=reference,
            amount_minor=int(total),
            status=PaymentTransactionStatus.SUCCESS,
        ),
    )

    # Write balanced ledger pair (client -X, escrow +X)
    escrow_utils.add_ledger_entries(
        session,
        [
            LedgerEntry(contract_id=contract.id, account=LedgerAccount.CLIENT, amount=-total),
            LedgerEntry(contract_id=contract.id, account=LedgerAccount.ESCROW, amount=total),
        ],
    )

    contract.status = ContractStatus.ACTIVE
    session.add(contract)

    response = FundContractOut(
        contract_id=contract.id,
        status=contract.status,
        funded_amount=total,
        reference=reference,
        checkout_url=checkout_url,
    )

    escrow_utils.save_idempotency_key(
        session,
        key=idempotency_key,
        endpoint=endpoint,
        response_json=response.model_dump_json(),
        status_code=201,
    )

    redis_client.invalidate_prefix(f"statement:{contract.id}")
    session.commit()
    return response, False


def handle_webhook(
    session: Session,
    raw_body: bytes,
    x_signature: str | None = None,
    x_paystack_signature: str | None = None,
) -> dict:
    """Dual-adapter webhook handler.
    Supports both:
    1. Standard Capstone Webhook (X-Signature, HMAC-SHA256 with WEBHOOK_SECRET)
    2. Paystack Webhook (X-Paystack-Signature, HMAC-SHA512 with PAYSTACK_SECRET_KEY)
    """
    if x_signature:
        if not verify_standard_webhook_signature(raw_body, x_signature):
            raise UnauthorizedError("invalid webhook signature", code="invalid_signature")
        return _handle_standard_webhook(session, raw_body)

    if x_paystack_signature:
        if not verify_paystack_webhook_signature(raw_body, x_paystack_signature):
            raise UnauthorizedError("invalid webhook signature", code="invalid_signature")
        return _handle_paystack_webhook(session, raw_body)

    raise UnauthorizedError("missing webhook signature", code="missing_signature")


def _handle_standard_webhook(session: Session, raw_body: bytes) -> dict:
    try:
        payload = json.loads(raw_body)
    except Exception as exc:
        raise ConflictError("malformed json payload", code="invalid_payload") from exc

    event_id = payload.get("event_id")
    event_type = payload.get("type", "payment.succeeded")
    reference = payload.get("reference")
    amount = payload.get("amount")

    if not event_id or not reference:
        return {"status": "ok", "message": "missing_fields"}

    if utils.get_processed_event(session, event_id) is not None:
        return {"status": "ok", "message": "already_processed"}

    utils.save_processed_event(session, event_id, str(reference))

    # Match reference to contract or transaction
    contract = None
    try:
        contract_uuid = uuid.UUID(str(reference))
        contract = contracts_utils.get_contract_by_id(session, contract_uuid)
    except (ValueError, TypeError):
        pass

    if contract is None:
        tx = utils.get_transaction_by_reference(session, str(reference))
        if tx:
            contract = contracts_utils.get_contract_by_id(session, tx.contract_id)
            utils.mark_transaction_status(session, tx, PaymentTransactionStatus.SUCCESS)

    if contract is not None:
        amount_dec = Decimal(str(amount)) if amount is not None else Decimal("0")
        if amount_dec <= Decimal("0"):
            milestones = contracts_utils.list_milestones_for_contract(session, contract.id)
            amount_dec = sum((Decimal(m.amount_minor) for m in milestones), Decimal("0"))
        escrow_services.confirm_funding(session, contract.id, amount_dec)
    else:
        logger.warning("webhook: unknown reference '%s' logged as orphan", reference)

    session.commit()
    return {"status": "ok"}


def _handle_paystack_webhook(session: Session, raw_body: bytes) -> dict:
    payload = json.loads(raw_body)
    event_type = payload.get("event")
    data = payload.get("data", {})
    reference = data.get("reference")

    if not reference:
        return {"status": "ok"}

    event_id = f"{event_type}:{reference}"
    if utils.get_processed_event(session, event_id) is not None:
        return {"status": "ok", "message": "already_processed"}

    if event_type == "charge.success":
        transaction = utils.get_transaction_by_reference(session, reference)
        if transaction is None:
            utils.save_processed_event(session, event_id, reference)
            session.commit()
            return {"status": "ok", "message": "orphan"}

        try:
            verify_response = paystack_client.transactions.verify_transaction(reference)
            verified_amount = verify_response.data.get("amount")
            verified_status = verify_response.data.get("status")
        except Exception:
            verified_amount = transaction.amount_minor
            verified_status = "success"

        if verified_status == "success" and verified_amount == transaction.amount_minor:
            escrow_services.confirm_funding(session, transaction.contract_id, Decimal(transaction.amount_minor))
            utils.mark_transaction_status(session, transaction, PaymentTransactionStatus.SUCCESS)
        else:
            utils.mark_transaction_status(session, transaction, PaymentTransactionStatus.FAILED)

    utils.save_processed_event(session, event_id, reference)
    session.commit()
    return {"status": "ok"}