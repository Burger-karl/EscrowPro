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
from app.src.escrow.schemas import LedgerEntryOut, StatementOut



def confirm_funding(session: Session, contract_id: uuid.UUID, total: Decimal) -> None:
    
    contract = utils.get_contract_for_update(session, contract_id)
    if contract is None:
        return  # nothing sensible to do — worth logging in real production use

    if contract.status != ContractStatus.DRAFT:
        return  # already funded — webhook redelivery, no-op

    utils.add_ledger_entries(
        session,
        [
            LedgerEntry(contract_id=contract.id, account=LedgerAccount.CLIENT, amount=-total),
            LedgerEntry(contract_id=contract.id, account=LedgerAccount.ESCROW, amount=total),
        ],
    )

    contract.status = ContractStatus.ACTIVE
    session.add(contract)
    session.commit()



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


def split_milestone(
        session: Session,
        milestone: Milestone,
        freelancer_percent: int
) -> tuple[int, int]:
    """Arbiter's ruling: escrow -total, freelancer +freelancer_amount, client +client_amount. Returns (freelancer_amount, client_amount)"""
    total = milestone.amount_minor
    freelancer_amount = total * freelancer_percent // 100
    client_amount = total - freelancer_amount

    escrow_balance = utils.get_balance(session, milestone.contract_id, LedgerAccount.ESCROW)
    if escrow_balance < total:
        raise ConflictError(
            "escrow does not hold enough funds to settle this dispute",
            code="insufficient_escrow_balance",
        )
    
    entries = [
        LedgerEntry(
            contract_id=milestone.contract_id, account=LedgerAccount.ESCROW, amount=-Decimal(total)
        )
    ]
    if freelancer_amount > 0:
        entries.append(
            LedgerEntry(
                contract_id=milestone.contract_id,
                account=LedgerAccount.FREELANCER,
                amount=Decimal(freelancer_amount),
            )
        )
    if client_amount > 0:
        entries.append(
            LedgerEntry(
                contract_id=milestone.contract_id,
                account=LedgerAccount.CLIENT,
                amount=Decimal(client_amount),
            )
        )
    utils.add_ledger_entries(session, entries)
    return freelancer_amount, client_amount


def record_payout(session: Session, contract_id: uuid.UUID, amount_minor: int) -> None:
    amount = Decimal(amount_minor)
    balance = utils.get_balance(session, contract_id, LedgerAccount.FREELANCER)
    if balance < amount:
        raise ConflictError(
            "freelancer balance is too low for this payout",
            code="insufficient_balance",
        )

    utils.add_ledger_entries(
        session,
        [
            LedgerEntry(contract_id=contract_id,
            account=LedgerAccount.FREELANCER,
            amount=-amount),
            LedgerEntry(contract_id=contract_id,
            account=LedgerAccount.PAYOUT, amount=amount),
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
        payout_balance=utils.get_balance(session, contract_id, LedgerAccount.PAYOUT),
        entries=[LedgerEntryOut.model_validate(e) for e in entries],
    )