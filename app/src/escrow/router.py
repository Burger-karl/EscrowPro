# import uuid
# from typing import Annotated

# from fastapi import APIRouter, Header, Response, status

# from app.core.dependencies import CurrentUser, DbSession
# from app.src.escrow import services
# from app.src.escrow.schemas import FundContractOut, StatementOut

# router = APIRouter(tags=["Escrow"])


# @router.post("/contracts/{contract_id}/fund", response_model=FundContractOut)
# def fund_contract(
#     contract_id: uuid.UUID,
#     session: DbSession,
#     user: CurrentUser,
#     response: Response,
#     idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
# ) -> FundContractOut:
#     result, is_replay = services.fund_contract(session, user, contract_id, idempotency_key)
#     response.status_code = status.HTTP_200_OK if is_replay else status.HTTP_201_CREATED
#     return result


# @router.get("/contracts/{contract_id}/statement", response_model=StatementOut)
# def get_statement(contract_id: uuid.UUID, session: DbSession, user: CurrentUser) -> StatementOut:
#     return services.get_statement(session, user, contract_id)




import uuid
from typing import Annotated

from fastapi import APIRouter, Header, Response, status

from app.core.dependencies import CurrentUser, DbSession
from app.src.escrow import services
from app.src.escrow.schemas import FundContractOut, StatementOut

router = APIRouter(tags=["Escrow"])


@router.post(
    "/contracts/{contract_id}/fund",
    response_model=FundContractOut,
    summary="Fund contract (client)",
)
def fund_contract(
    contract_id: uuid.UUID,
    session: DbSession,
    user: CurrentUser,
    response: Response,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
) -> FundContractOut:
    """
    201 the first time a contract is funded. 200 if the same
    Idempotency-Key is replayed (the client retried — same result,
    nothing new happened). 403 if not the contract's client, 404 if
    not found, 409 if already funded or has no milestones, 422 if the
    Idempotency-Key header is missing.
    """
    result, is_replay = services.fund_contract(session, user, contract_id, idempotency_key)
    response.status_code = status.HTTP_200_OK if is_replay else status.HTTP_201_CREATED
    return result


@router.get(
    "/contracts/{contract_id}/statement",
    response_model=StatementOut,
    summary="Get contract statement (party or arbiter)",
)
def get_statement(contract_id: uuid.UUID, session: DbSession, user: CurrentUser) -> StatementOut:
    """200 on success. 403 if the caller isn't a party or an arbiter, 404 if not found."""
    return services.get_statement(session, user, contract_id)