import logging
import uuid

from sqlmodel import Session

from app.core.errors import AppError, ConflictError, ForbiddenError, NotFoundError
from app.db.base import utcnow
from app.platform.events.broadcaster import broadcaster, make_event
from app.src.accounts.models import User, UserRole
from app.src.contracts import services as contracts_services
from app.src.contracts import utils as contracts_utils
from app.src.contracts.models import Contract, Milestone, MilestoneStatus
from app.src.disputes import firestore_client, utils
from app.src.disputes.models import Dispute, DisputeStatus
from app.src.disputes.schemas import DisputeOpenIn, DisputeResolveIn, MessageIn, MessageOut
from app.src.escrow import services as escrow_services
from app.src.escrow import utils as escrow_utils

logger = logging.getLogger(__name__)


def dispute_topic(dispute_id: uuid.UUID) -> str:
    """The Broadcaster topic every stream of this dispute listens on."""
    return f"dispute:{dispute_id}"


def author_role(user: User, contract: Contract) -> str:
    """Return the user's role in the contract for a dispute message."""
    if user.id == contract.client_id:
        return "client"
    if user.id == contract.freelancer_id:
        return "freelancer"
    return "arbiter"


def _load_dispute_context(
        session: Session, dispute: Dispute | None
) -> tuple[Dispute, Milestone, Contract]:
    if dispute is None:
        raise NotFoundError("dispute not found", code="dispute_not_found")

    milestone = contracts_utils.get_milestone_by_id(session, dispute.milestone_id)
    contract = contracts_utils.get_contract_by_id(session, milestone.contract_id)
    return dispute, milestone, contract


def get_dispute_for_viewer(session: Session, user: User, dispute_id: uuid.UUID) -> Dispute:
    """Loads a dispute if the user is one of its parties or the arbiter (else 404 / 403)."""
    dispute, _, contract = _load_dispute_context(session, utils.get_dispute_by_id(session, dispute_id))
    contracts_services.require_party_or_arbiter(contract, user)
    return dispute


def open_dispute(session: Session, user: User, data: DisputeOpenIn) -> Dispute:
    """Opens a dispute if the user is the client or the freelancer (else 403)."""
    milestone = contracts_utils.get_milestone_by_id(session, data.milestone_id)
    if milestone is None:
        raise NotFoundError("milestone not found", code="milestone_not_found")

    #Lock the contract, then re-read the milestone, so opening a dispute and approving the same milestone can't both win
    contract = escrow_utils.get_contract_for_update(session, milestone.contract_id)
    session.refresh(milestone)

    if user.id not in (contract.client_id, contract.freelancer_id):
        raise ForbiddenError("you are not a party to this contract", code="not_a_party")

    if milestone.status != MilestoneStatus.SUBMITTED:
        raise ConflictError(
            f"a dispute can only be opened for a submitted milestone "
            f"(this one is '{milestone.status.value}')",
            code="milestone_not_disputable",
        )

    dispute = Dispute(milestone_id=milestone.id, opened_by=user.id)
    utils.add_dispute(session, dispute)

    # DISPUTED freezes the milestone: approve and submit both reject it with 409.
    milestone.status = MilestoneStatus.DISPUTED
    session.add(milestone)
    session.commit()
    session.refresh(dispute)


    # Postgres is the source of truth and is already committed. The thread document is only metadata, so a Firestore hiccup must not undo the dispute.

    try:
        firestore_client.create_thread(dispute.id, milestone.id, user.id, dispute.created_at)
    except Exception:
        logger.exception("could not create Firestore thread for dispute %s", dispute.id)

    return dispute


def post_message(session: Session, user: User, dispute_id: uuid.UUID, data: MessageIn) -> MessageOut:
    dispute, _, contract = _load_dispute_context(session, utils.get_dispute_by_id(session, dispute_id))
    contracts_services.require_party_or_arbiter(contract, user)

    if dispute.status != DisputeStatus.OPEN:
        raise ConflictError(
            "this dispute is resolved, its thread is closed",
            code="dispute_closed",
        )

    message = MessageOut(
        id=uuid.uuid4(),
        dispute_id=dispute_id,
        author_id=user.id,
        author_role=author_role(user, contract),
        body=data.body,
        created_at=utcnow(),
    )


    # Firestore first: if it fails, nobody has been told about a message that was never stored.

    try:
        document = {**message.model_dump(mode="json"), "created_at": message.created_at}
        firestore_client.add_message(dispute_id, document)
    except Exception as exc:
        logger.exception("could not write message to Firestore for dispute %s", dispute_id)
        raise AppError(
            "the dispute thread is temporarily unavailable, please retry",
            code="thread_unavailable",
            status_code=503,
        ) from exc

    broadcaster.publish(
        dispute_topic(dispute_id),
        make_event("message.created", str(message.id), message.model_dump(mode="json")),
    )

    return message


def resolve_dispute(
        session: Session,
        arbiter: User,
        dispute_id: uuid.UUID,
        data: DisputeResolveIn,
) -> Dispute:
    if arbiter.role != UserRole.ARBITER:
        raise ForbiddenError("only the arbiter can resolve disputes", code="role_not_allowed")

    dispute, milestone, _ = _load_dispute_context(
        session, utils.get_dispute_for_update(session, dispute_id)
    )
    if dispute.status != DisputeStatus.OPEN:
        raise ConflictError(
            "this dispute is already resolved, its thread is closed",
            code="dispute_already_resolved",
        )

    contract = escrow_utils.get_contract_for_update(session, milestone.contract_id)

    freelancer_amount, client_amount = escrow_services.split_milestone(
        session, milestone, data.freelancer_percent
    )

    dispute.status = DisputeStatus.RESOLVED
    dispute.updated_at = utcnow()
    dispute.resolution_json = {
        "freelancer_percent": data.freelancer_percent,
        "client_percent": 100 - data.freelancer_percent,
        "freelancer_amount": freelancer_amount,
        "client_amount": client_amount,
        "note": data.note,
        "resolved_by": str(arbiter.id),
    }
    milestone.status = MilestoneStatus.RESOLVED
    session.add(dispute)
    session.add(milestone)
    session.flush()
    contracts_services.complete_contract_if_all_milestones_approved(session, contract)
    session.commit()
    session.refresh(dispute)

    _announce_resolution(dispute)
    return dispute


def _announce_resolution(dispute: Dispute) -> None:
    try:
        firestore_client.mark_thread_resolved(dispute.id, dispute.resolution_json)
    except Exception:
        logger.exception("could not mark Firestore thread resolve for dispute %s", dispute.id)

    broadcaster.publish(
        dispute_topic(dispute.id),
        make_event("dispute.resolved", str(dispute.id), dispute.resolution_json),
    )




