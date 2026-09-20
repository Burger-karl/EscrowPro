import uuid

from fastapi import APIRouter, status

from app.core.dependencies import CurrentUser, DbSession
from app.src.contracts import services
from app.src.contracts.schemas import ContractCreateIn, ContractOut, MilestoneOut

router = APIRouter(tags=["Contracts"])


@router.post("/contracts", response_model=ContractOut, status_code=status.HTTP_201_CREATED)
def create_contract(data: ContractCreateIn, session: DbSession, user: CurrentUser) -> ContractOut:
    """201 on success, 401 if unauthenticated, 422 on bad input.
    Only clients may create contracts (403 otherwise, raised in the service)."""
    contract = services.create_contract(session, user, data)
    return ContractOut.model_validate(contract)


@router.get("/contracts/{contract_id}", response_model=ContractOut)
def get_contract(contract_id: uuid.UUID, session: DbSession, user: CurrentUser) -> ContractOut:
    """200 on success. 403 if the caller isn't a party or an arbiter, 404 if not found."""
    contract = services.get_contract(session, user, contract_id)
    return ContractOut.model_validate(contract)


@router.post("/milestones/{milestone_id}/submit", response_model=MilestoneOut)
def submit_milestone(milestone_id: uuid.UUID, session: DbSession, user: CurrentUser) -> MilestoneOut:
    """200 on success. 403 if not the assigned freelancer, 404 if not found,
    409 if the milestone isn't in a submittable state."""
    milestone = services.submit_milestone(session, user, milestone_id)
    return MilestoneOut.model_validate(milestone)


@router.post("/milestones/{milestone_id}/approve", response_model=MilestoneOut)
def approve_milestone(milestone_id: uuid.UUID, session: DbSession, user: CurrentUser) -> MilestoneOut:
    """200 on success. 403 if not the contract's client, 404 if not found,
    409 if the milestone isn't awaiting approval."""
    milestone = services.approve_milestone(session, user, milestone_id)
    return MilestoneOut.model_validate(milestone)