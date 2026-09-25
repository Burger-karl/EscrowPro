import logging
import uuid

from sqlmodel import Session

from app.core.errors import AppError, ConflictError, ForbiddenError, NotFoundError
from app.db.base import utcnow
from app.platform.events.broadcaster import broadcaster, make_event
from app.src.accounts.models import User, UserRole
from app.src.contracts import services as contracts_services
from app.src.contracts import utils as contracts_utils
from app.src.contracts.models import Contract, ContractStatus, Milestone, MilestoneStatus
from app.src.disputes import firestore_client, utils
from app.src.disputes.models import Dispute, DisputeStatus
from app.src.disputes.schemas import DisputeOpenIn, DisputeResolveIn, MessageIn, MessageOut
from app.src.escrow import services as escrow_services
from app.src.escrow import utils as escrow_utils

logger = logging.getLogger(__name__)

UNSETTLED_MILESTONE_STATUSES = (
    MilestoneStatus.PENDING,
    MilestoneStatus.SUBMITTED,
    MilestoneStatus.REJECTED,
)


def dispute_topic(dispute_id: uuid.UUID) -> str:
    return f"dispute:{dispute_id}"


def author_role(user: User, contract: Contract) -> str:
    if user.id == contract.client_id:
        return "client"
    if user.id == contract.freelancer_id:
        return "freelancer"
    if user.role == UserRole.ADMIN:
        return "admin"
    return "arbiter"


def _load_dispute_context(
    session: Session, dispute: Dispute | None
) -> tuple[Dispute, Contract, Milestone | None]:
    if dispute is None:
        raise NotFoundError("dispute not found", code="dispute_not_found")
    contract = contracts_utils.get_contract_by_id(session, dispute.contract_id)
    milestone = (
        contracts_utils.get_milestone_by_id(session, dispute.milestone_id)
        if dispute.milestone_id is not None
        else None
    )
    return dispute, contract, milestone


def get_dispute_for_viewer(session: Session, user: User, dispute_id: uuid.UUID) -> Dispute:
    dispute, contract, _ = _load_dispute_context(session, utils.get_dispute_by_id(session, dispute_id))
    contracts_services.require_party_or_arbiter(contract, user)
    return dispute


def open_dispute(session: Session, user: User, data: DisputeOpenIn) -> Dispute:
    contract = escrow_utils.get_contract_for_update(session, data.contract_id)
    if contract is None:
        raise NotFoundError("contract not found", code="contract_not_found")

    if user.id not in (contract.client_id, contract.freelancer_id):
        raise ForbiddenError("only a party to this contract can open a dispute", code="not_a_party")

    # Only one dispute open per contract at a time — milestone-scoped and contract-scoped disputes can't be live together, so there's never more than one arbiter ruling in flight for the same money.

    if utils.get_open_dispute_for_contract(session, contract.id) is not None:
        raise ConflictError(
            "a dispute is already open on this contract", code="dispute_already_open"
        )

    milestone: Milestone | None = None

    if data.milestone_id is not None:
        milestone = contracts_utils.get_milestone_by_id(session, data.milestone_id)
        if milestone is None or milestone.contract_id != contract.id:
            raise NotFoundError(
                "milestone not found on this contract", code="milestone_not_found"
            )
        if milestone.status != MilestoneStatus.SUBMITTED:
            raise ConflictError(
                f"a dispute can only be opened on a submitted milestone "
                f"(this one is '{milestone.status.value}')",
                code="milestone_not_disputable",
            )
        milestone.status = MilestoneStatus.DISPUTED
        session.add(milestone)
    else:
        if contract.status != ContractStatus.ACTIVE:
            raise ConflictError(
                f"a contract-level dispute can only be opened while the "
                f"contract is active (this one is '{contract.status.value}')",
                code="contract_not_disputable",
            )
        contract.status = ContractStatus.DISPUTED
        session.add(contract)

    dispute = Dispute(
        contract_id=contract.id,
        milestone_id=milestone.id if milestone else None,
        opened_by=user.id,
    )
    utils.add_dispute(session, dispute)
    session.commit()
    session.refresh(dispute)

    # Postgres is the source of truth and is already committed. The thread document is only metadata, so a Firestore hiccup must not undo the dispute.
    try:
        firestore_client.create_thread(
            dispute.id, contract.id, dispute.milestone_id, user.id, dispute.created_at
        )
    except Exception:
        logger.exception("could not create Firestore thread for dispute %s", dispute.id)

    return dispute




def post_message(
    session: Session, user: User, dispute_id: uuid.UUID, data: MessageIn
) -> MessageOut:
    dispute, contract, _ = _load_dispute_context(session, utils.get_dispute_by_id(session, dispute_id))
    contracts_services.require_party_or_arbiter(contract, user)

    if dispute.status != DisputeStatus.OPEN:
        raise ConflictError("this dispute is resolved, its thread is closed", code="dispute_closed")

    message = MessageOut(
        id=uuid.uuid4(),
        dispute_id=dispute.id,
        author_id=user.id,
        author_role=author_role(user, contract),
        body=data.body,
        created_at=utcnow(),
    )

    try:
        document = {**message.model_dump(mode="json"), "created_at": message.created_at}
        firestore_client.add_message(dispute.id, document)
    except Exception as exc:
        logger.exception("could not write message to Firestore for dispute %s", dispute.id)
        raise AppError(
            "the dispute thread is temporarily unavailable, please retry",
            code="thread_unavailable",
            status_code=503,
        ) from exc

    broadcaster.publish(
        dispute_topic(dispute.id),
        make_event("message.created", str(message.id), message.model_dump(mode="json")),
    )
    return message


def resolve_dispute(
    session: Session, arbiter: User, dispute_id: uuid.UUID, data: DisputeResolveIn
) -> Dispute:
    if arbiter.role not in (UserRole.ARBITER, UserRole.ADMIN):
        raise ForbiddenError("only the arbiter can resolve disputes", code="role_not_allowed")

    dispute, _, milestone = _load_dispute_context(
        session, utils.get_dispute_for_update(session, dispute_id)
    )
    if dispute.status != DisputeStatus.OPEN:
        raise ConflictError("this dispute is already resolved", code="dispute_already_resolved")

    # Same contract lock every other money movement takes.
    contract = escrow_utils.get_contract_for_update(session, dispute.contract_id)

    if milestone is not None:
        entries = [_settle_one_milestone(session, milestone, data.freelancer_percent)]
        scope = "milestone"
    else:
        unsettled = [
            m
            for m in contracts_utils.list_milestones_for_contract(session, contract.id)
            if m.status in UNSETTLED_MILESTONE_STATUSES
        ]
        if not unsettled:
            raise ConflictError(
                "there is nothing left in escrow on this contract to resolve",
                code="nothing_to_resolve",
            )
        entries = [_settle_one_milestone(session, m, data.freelancer_percent) for m in unsettled]
        scope = "contract"
        
        contract.status = ContractStatus.ACTIVE
        session.add(contract)

    dispute.status = DisputeStatus.RESOLVED
    dispute.updated_at = utcnow()
    dispute.resolution_json = {
        "scope": scope,
        "freelancer_percent": data.freelancer_percent,
        "client_percent": 100 - data.freelancer_percent,
        "note": data.note,
        "resolved_by": str(arbiter.id),
        "milestones": entries,
    }
    session.add(dispute)
    session.flush()

    contracts_services.complete_contract_if_all_milestones_approved(session, contract)

    session.commit()
    session.refresh(dispute)

    _announce_resolution(dispute)
    return dispute


def _settle_one_milestone(session: Session, milestone: Milestone, freelancer_percent: int) -> dict:
    """Splits one milestone's amount and marks it RESOLVED. Flushes only."""
    freelancer_amount, client_amount = escrow_services.split_milestone(
        session, milestone, freelancer_percent
    )
    milestone.status = MilestoneStatus.RESOLVED
    session.add(milestone)
    return {
        "milestone_id": str(milestone.id),
        "amount_minor": milestone.amount_minor,
        "freelancer_amount": freelancer_amount,
        "client_amount": client_amount,
    }



def _announce_resolution(dispute: Dispute) -> None:
    try:
        firestore_client.mark_thread_resolved(dispute.id, dispute.resolution_json)
    except Exception:
        logger.exception("could not mark Firestore thread resolve for dispute %s", dispute.id)

    broadcaster.publish(
        dispute_topic(dispute.id),
        make_event("dispute.resolved", str(dispute.id), dispute.resolution_json),
    )




