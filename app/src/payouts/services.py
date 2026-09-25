import uuid

from sqlmodel import Session

from app.core.errors import ConflictError, ForbiddenError, NotFoundError
from app.db.base import utcnow
from app.src.accounts.models import User, UserRole
from app.src.contracts import utils as contracts_utils
from app.src.contracts.models import Milestone, MilestoneStatus
from app.src.disputes import utils as disputes_utils
from app.src.escrow import services as escrow_services
from app.src.escrow import utils as escrow_utils
from app.src.escrow.models import LedgerAccount
from app.src.payouts import utils
from app.src.payouts.models import Payout, PayoutStatus
from app.src.payouts.schemas import PayoutCreateIn


def _payable_amount(session: Session, milestone: Milestone) -> int:
    """What the freelancer is actually owed for this milestone.

    Approved: the full milestone amount. Resolved: the freelancer's share from
    whichever dispute settled it — a dispute opened directly on this milestone,
    or a contract-level dispute whose payout covered it (both are recorded the
    same way, see disputes/utils.get_resolution_for_milestone).
    """
    if milestone.status == MilestoneStatus.APPROVED:
        return milestone.amount_minor

    if milestone.status == MilestoneStatus.RESOLVED:
        resolution = disputes_utils.get_resolution_for_milestone(
            session, milestone.contract_id, milestone.id
        )
        if resolution is None:
            return 0
        return resolution["freelancer_amount"]

    raise ConflictError(
        f"a payout can only be requested for an approved or resolved milestone "
        f"(this one is '{milestone.status.value}')",
        code="milestone_not_approved",
    )


def request_payout(session: Session, freelancer: User, data: PayoutCreateIn) -> Payout:
    if freelancer.role != UserRole.FREELANCER:
        raise ForbiddenError("only freelancers can request payouts", code="role_not_allowed")

    milestone = contracts_utils.get_milestone_by_id(session, data.milestone_id)
    if milestone is None:
        raise NotFoundError("milestone not found", code="milestone_not_found")

    # Lock the contract row so two simultaneous requests for the same milestone queue up instead of both passing the checks below.
    contract = escrow_utils.get_contract_for_update(session, milestone.contract_id)
    if contract is None or contract.freelancer_id != freelancer.id:
        raise ForbiddenError(
            "this milestone does not belong to one of your contracts",
            code="not_assigned_freelancer",
        )

    amount = _payable_amount(session, milestone)
    if amount <= 0:
        raise ConflictError("there is nothing to pay out for this milestone", code="nothing_to_pay_out")

    if utils.get_payout_by_milestone_id(session, milestone.id) is not None:
        raise ConflictError(
            "a payout has already been requested for this milestone",
            code="payout_already_requested",
        )

    # Available = what the ledger says the freelancer holds on this contract, minus payouts already requested but not yet sent.
    balance = escrow_utils.get_balance(session, contract.id, LedgerAccount.FREELANCER)
    pending = utils.sum_pending_for_contract(session, contract.id)
    if balance - pending < amount:
        raise ConflictError(
            "insufficient available balance for this payout",
            code="insufficient_balance",
        )

    payout = Payout(
        freelancer_id=freelancer.id,
        milestone_id=milestone.id,
        amount_minor=amount,
    )
    utils.add_payout(session, payout)
    session.commit()
    session.refresh(payout)
    return payout


def mark_payout_sent(session: Session, finance_user: User, payout_id: uuid.UUID) -> Payout:
    if finance_user.role not in (UserRole.FINANCE, UserRole.ADMIN):
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

    # Same contract lock the release and funding paths use, so the balance check and the ledger write below can't interleave with another move.
    escrow_utils.get_contract_for_update(session, milestone.contract_id)

    # Money leaves the system here: ledger pair (freelancer -X, payout +X),
    # in the same transaction as the status change below.
    escrow_services.record_payout(session, milestone.contract_id, payout.amount_minor)

    payout.status = PayoutStatus.SENT
    payout.updated_at = utcnow()
    session.add(payout)
    session.commit()
    session.refresh(payout)
    return payout