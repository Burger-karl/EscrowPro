import uuid

from sqlmodel import Session

from app.core.errors import ConflictError, ForbiddenError, NotFoundError
from app.src.accounts.models import User, UserRole
from app.src.contracts import utils
from app.src.contracts.models import Contract, ContractStatus, Milestone, MilestoneStatus
from app.src.contracts.schemas import ContractCreateIn
from app.src.escrow import utils as escrow_utils
from app.src.escrow.services import release_milestone as escrow_release_milestone


def create_contract(session: Session, client: User, data: ContractCreateIn) -> Contract:
    if client.role != UserRole.CLIENT:
        raise ForbiddenError("only clients can create contracts", code="role_not_allowed")

    contract = Contract(
        client_id=client.id,
        freelancer_id=data.freelancer_id,
        title=data.title,
        description=data.description,
        status=ContractStatus.DRAFT,
    )
    milestones = [
        Milestone(title=m.title, description=m.description, amount_minor=m.amount_minor, sequence=i)
        for i, m in enumerate(data.milestones)
    ]
    return utils.create_contract_with_milestones(session, contract, milestones)


def require_party_or_arbiter(contract: Contract, user: User) -> None:
    is_party = user.id in (contract.client_id, contract.freelancer_id)
    is_arbiter = user.role == UserRole.ARBITER
    if not (is_party or is_arbiter):
        raise ForbiddenError(
            "you are not a party to this contract",
            code="not_a_party",
        )


def get_contract(session: Session, user: User, contract_id: uuid.UUID) -> Contract:
    contract = utils.get_contract_by_id(session, contract_id)
    if contract is None:
        raise NotFoundError("contract not found", code="contract_not_found")

    require_party_or_arbiter(contract, user)
    return contract


def get_milestone(session: Session, user: User, milestone_id: uuid.UUID) -> Milestone:
    """Fetches one milestone (its description, amount, status) for a party or the arbiter — e.g. so an arbiter can see what a disputed milestone is actually about before resolving it."""
    milestone = utils.get_milestone_by_id(session, milestone_id)
    if milestone is None:
        raise NotFoundError("milestone not found", code="milestone_not_found")

    contract = utils.get_contract_by_id(session, milestone.contract_id)
    if contract is None:
        raise NotFoundError("milestone not found", code="milestone_not_found")

    require_party_or_arbiter(contract, user)
    return milestone



def submit_milestone(session: Session, freelancer: User, milestone_id: uuid.UUID) -> Milestone:
    milestone = utils.get_milestone_by_id(session, milestone_id)
    if milestone is None:
        raise NotFoundError("milestone not found", code="milestone_not_found")

    # Lock the contract so this can't land in the middle of a dispute being opened on it (which also needs the same lock before it changes status).
    # This is a bit of a hack, but it's the only way to do it without a transaction.

    contract = escrow_utils.get_contract_for_update(session, milestone.contract_id)
    session.refresh(milestone)

    if contract is None or contract.freelancer_id != freelancer.id:
        raise ForbiddenError(
            "only the assigned freelancer can submit this milestone",
            code="not_assigned_freelancer",
        )

    if contract.status != ContractStatus.ACTIVE:
        raise ConflictError(
            f"the contract is not active (status '{contract.status.value}')",
            code="contract_not_active",
        )

    if milestone.status not in (MilestoneStatus.PENDING, MilestoneStatus.REJECTED):
        raise ConflictError(
            f"milestone cannot be submitted from status '{milestone.status.value}'",
            code="invalid_milestone_state",
        )

    milestone.status = MilestoneStatus.SUBMITTED
    session.add(milestone)
    session.commit()
    session.refresh(milestone)
    return milestone



def approve_milestone(session: Session, client: User, milestone_id: uuid.UUID) -> Milestone:
    milestone = utils.get_milestone_by_id(session, milestone_id)
    if milestone is None:
        raise NotFoundError("milestone not found", code="milestone_not_found")

    contract = escrow_utils.get_contract_for_update(session, milestone.contract_id)
    session.refresh(milestone)

    if contract is None or contract.client_id != client.id:
        raise ForbiddenError(
            "only the contract's client can approve this milestone",
            code="not_contract_client",
        )

    if contract.status != ContractStatus.ACTIVE:
        raise ConflictError(
            f"the contract is not active (status '{contract.status.value}')",
            code="contract_not_active",
        )

    if milestone.status != MilestoneStatus.SUBMITTED:
        raise ConflictError(
            f"milestone cannot be approved from status '{milestone.status.value}'",
            code="invalid_milestone_state",
        )

    milestone.status = MilestoneStatus.APPROVED
    session.add(milestone)
    session.flush()

    
    escrow_release_milestone(session, milestone)

    complete_contract_if_all_milestones_approved(session, contract)

    session.commit()
    session.refresh(milestone)
    return milestone


def complete_contract_if_all_milestones_approved(session: Session, contract: Contract) -> None:
    all_milestones = utils.list_milestones_for_contract(session, contract.id)
    settled = (MilestoneStatus.APPROVED, MilestoneStatus.RESOLVED)
    if all(m.status in settled for m in all_milestones):
        contract.status = ContractStatus.COMPLETED
        session.add(contract)