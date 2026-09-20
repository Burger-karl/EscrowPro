import json
import uuid
from decimal import Decimal

from sqlmodel import Session

from app.core.errors import ConflictError, ForbiddenError, NotFoundError
from app.src.accounts.models import User, UserRole
from app.src.contracts import utils as contracts_utils
from app.src.contracts.models import Contract, ContractStatus, Milestone
from app.src.escrow import utils
from app.src.escrow.models import LedgerAccount, LedgerEntry
from app.src.escrow.schemas import FundContractOut, LedgerEntryOut, StatementOut


def fund_contract(
    session: Session,
    client: User,
    contract_id: uuid.UUID,
    idempotency_key: str,
) -> tuple[FundContractOut, bool]:
    
    endpoint = f"/contracts/{contract_id}/fund"

    existing = utils.get_idempotency_key(session, idempotency_key)
    if existing is not None:
        if existing.endpoint != endpoint:
            # Same key reused against a different endpoint is a client
            # bug, not something we should silently paper over.
            raise ConflictError(
                "this idempotency key was already used for a different request",
                code="idempotency_key_reused",
            )
        return FundContractOut.model_validate(json.loads(existing.response_json)), True

    contract = utils.get_contract_for_update(session, contract_id)
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

    utils.add_ledger_entries(
        session,
        [
            LedgerEntry(contract_id=contract.id, account=LedgerAccount.CLIENT, amount=-total),
            LedgerEntry(contract_id=contract.id, account=LedgerAccount.ESCROW, amount=total),
        ],
    )

    contract.status = ContractStatus.ACTIVE
    session.add(contract)

    response = FundContractOut(
        contract_id=contract.id, status=contract.status, funded_amount=total
    )

    utils.save_idempotency_key(
        session,
        key=idempotency_key,
        endpoint=endpoint,
        response_json=response.model_dump_json(),
        status_code=201,
    )

    session.commit()
    return response, False


def release_milestone(session: Session, milestone: Milestone) -> None:
    
    amount = Decimal(milestone.amount_minor)
    utils.add_ledger_entries(
        session,
        [
            LedgerEntry(
                contract_id=milestone.contract_id, account=LedgerAccount.ESCROW, amount=-amount
            ),
            LedgerEntry(
                contract_id=milestone.contract_id,
                account=LedgerAccount.FREELANCER,
                amount=amount,
            ),
        ],
    )


def get_statement(session: Session, user: User, contract_id: uuid.UUID) -> StatementOut:
    contract = contracts_utils.get_contract_by_id(session, contract_id)
    if contract is None:
        raise NotFoundError("contract not found", code="contract_not_found")

    is_party = user.id in (contract.client_id, contract.freelancer_id)
    is_arbiter = user.role == UserRole.ARBITER
    if not (is_party or is_arbiter):
        raise ForbiddenError("you are not a party to this contract", code="not_a_party")

    entries = utils.list_entries_for_contract(session, contract_id)

    return StatementOut(
        contract_id=contract_id,
        client_balance=utils.get_balance(session, contract_id, LedgerAccount.CLIENT),
        escrow_balance=utils.get_balance(session, contract_id, LedgerAccount.ESCROW),
        freelancer_balance=utils.get_balance(session, contract_id, LedgerAccount.FREELANCER),
        entries=[LedgerEntryOut.model_validate(e) for e in entries],
    )