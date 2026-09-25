import uuid

from fastapi import APIRouter, BackgroundTasks, status

from app.core.dependencies import CurrentUser, DbSession
from app.platform.tasks.background import notify_milestone_approved, notify_milestone_submitted
from app.src.accounts import utils as accounts_utils
from app.src.contracts import services, utils as contracts_utils
from app.src.contracts.schemas import ContractCreateIn, ContractOut, MilestoneOut

router = APIRouter(tags=["Contracts"])


@router.post(
    "/contracts",
    response_model=ContractOut,
    status_code=status.HTTP_201_CREATED,
    summary="[Role: Client] Create contract",
    description="Creates a new draft contract with milestones and assigns a freelancer. Accessible by: Client.",
)
def create_contract(data: ContractCreateIn, session: DbSession, user: CurrentUser) -> ContractOut:
    """201 on success, 401 if unauthenticated, 422 on bad input.
    Only clients may create contracts (403 otherwise, raised in the service)."""
    contract = services.create_contract(session, user, data)
    return ContractOut.model_validate(contract)


@router.get(
    "/contracts/{contract_id}",
    response_model=ContractOut,
    summary="[Role: Client, Freelancer, Arbiter, Admin] Get contract details",
    description="Retrieves contract details and its milestones. Accessible by: Client (contract owner), Freelancer (assigned), Arbiter, Admin.",
)
def get_contract(contract_id: uuid.UUID, session: DbSession, user: CurrentUser) -> ContractOut:
    """200 on success. 403 if the caller isn't a party or an arbiter, 404 if not found."""
    contract = services.get_contract(session, user, contract_id)
    return ContractOut.model_validate(contract)


@router.get(
    "/milestones/{milestone_id}",
    response_model=MilestoneOut,
    summary="[Role: Client, Freelancer, Arbiter, Admin] Get milestone details",
    description="Retrieves milestone information and status. Accessible by: Client (contract owner), Freelancer (assigned), Arbiter, Admin.",
)
def get_milestone(milestone_id: uuid.UUID, session: DbSession, user: CurrentUser) -> MilestoneOut:
    """200 on success. 403 if the caller isn't a party or an arbiter, 404 if not found.
    Handy for an arbiter looking up a disputed milestone's description and amount."""
    milestone = services.get_milestone(session, user, milestone_id)
    return MilestoneOut.model_validate(milestone)


@router.post(
    "/milestones/{milestone_id}/submit",
    response_model=MilestoneOut,
    summary="[Role: Freelancer] Submit milestone work",
    description="Submits completed milestone work for client review and notifies client. Accessible by: Assigned Freelancer.",
)
def submit_milestone(
    milestone_id: uuid.UUID,
    session: DbSession,
    user: CurrentUser,
    background_tasks: BackgroundTasks,
) -> MilestoneOut:
    """200 on success. 403 if not the assigned freelancer, 404 if not found,
    409 if the milestone isn't in a submittable state."""
    milestone = services.submit_milestone(session, user, milestone_id)
    contract = contracts_utils.get_contract_by_id(session, milestone.contract_id)
    if contract:
        client_user = accounts_utils.get_user_by_id(session, contract.client_id)
        if client_user:
            background_tasks.add_task(notify_milestone_submitted, client_user.email, milestone.title)
    return MilestoneOut.model_validate(milestone)


@router.post(
    "/milestones/{milestone_id}/approve",
    response_model=MilestoneOut,
    summary="[Role: Client] Approve milestone & release escrow",
    description="Approves submitted milestone, releases escrow funds to freelancer, and deducts platform fee. Accessible by: Contract Client.",
)
def approve_milestone(
    milestone_id: uuid.UUID,
    session: DbSession,
    user: CurrentUser,
    background_tasks: BackgroundTasks,
) -> MilestoneOut:
    """200 on success. 403 if not the contract's client, 404 if not found,
    409 if the milestone isn't awaiting approval."""
    milestone = services.approve_milestone(session, user, milestone_id)
    contract = contracts_utils.get_contract_by_id(session, milestone.contract_id)
    if contract:
        freelancer_user = accounts_utils.get_user_by_id(session, contract.freelancer_id)
        if freelancer_user:
            background_tasks.add_task(
                notify_milestone_approved,
                freelancer_user.email,
                milestone.title,
                milestone.amount_minor,
            )
    return MilestoneOut.model_validate(milestone)