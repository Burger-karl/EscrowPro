import uuid

from sqlmodel import Session

from app.core.errors import ConflictError, ForbiddenError, NotFoundError
from app.db.base import utcnow
from app.src.accounts.models import User, UserRole
from app.src.contracts import utils as contracts_utils
from app.src.contracts.models import MilestoneStatus
from app.src.escrow import services as escrow_services
from app.src.escrow import utils as escrow_utils
from app.src.escrow.models import LedgerAccount
from app.src.payouts import utils
from app.src.payouts.models import Payout, PayoutStatus
from app.src.payouts.schemas import PayoutCreateIn


def request_payout(session: Session, freelancer: User, data: PayoutCreateIn) -> Payout:
    if freelancer.role != UserRole.FREELANCER:
        raise ForbiddenError("only freelancers can request payouts", code="role_not_allowed")

    milestone = contracts_utils.get_milestone_by_id(session, data.milestone_id)
    if milestone is None:
        raise NotFoundError("milestone not found", code="milestone_not_found")

    
    contract = escrow_utils.get_contract_for_update(session, milestone.contract_id)
    if contract is None or contract.freelancer_id != freelancer.id:
        raise ForbiddenError(
            "this milestone does not belong to one of your contracts",
            code="not_assigned_freelancer",
        )

    if milestone.status != MilestoneStatus.APPROVED:
        raise ConflictError(
            f"a payout can only be requested for an approved milestone "
            f"(this one is '{milestone.status.value}')",
            code="milestone_not_approved",
        )

    if utils.get_payout_by_milestone_id(session, milestone.id) is not None:
        raise ConflictError(
            "a payout has already been requested for this milestone",
            code="payout_already_requested",
        )

    
    balance = escrow_utils.get_balance(session, contract.id, LedgerAccount.FREELANCER)
    pending = utils.sum_pending_for_contract(session, contract.id)
    if balance - pending < milestone.amount_minor:
        raise ConflictError(
            "insufficient available balance for this payout",
            code="insufficient_balance",
        )

    payout = Payout(
        freelancer_id=freelancer.id,
        milestone_id=milestone.id,
        amount_minor=milestone.amount_minor,
    )
    utils.add_payout(session, payout)
    session.commit()
    session.refresh(payout)
    return payout


def mark_payout_sent(session: Session, finance_user: User, payout_id: uuid.UUID) -> Payout:
    if finance_user.role != UserRole.FINANCE:
        raise ForbiddenError("only finance can mark payouts as sent", code="role_not_allowed")

    payout = utils.get_payout_for_update(session, payout_id)
    if payout is None:
        raise NotFoundError("payout not found", code="payout_not_found")

    if payout.status != PayoutStatus.PENDING:
        raise ConflictError(
            f"payout cannot be marked sent from status '{payout.status.value}'",
            code="invalid_payout_state",
        )

    milestone = contracts_utils.get_milestone_by_id(session, payout.milestone_id)

    
    escrow_utils.get_contract_for_update(session, milestone.contract_id) 
    # Lock the contract row so two simultaneous requests for the same milestone queue up instead of both passing the checks below.

    
    escrow_services.record_payout(session, milestone.contract_id, payout.amount_minor)
    # Record the payout in the escrow ledger.

    payout.status = PayoutStatus.SENT
    payout.updated_at = utcnow()
    session.add(payout)
    session.commit()
    session.refresh(payout)
    return payout
