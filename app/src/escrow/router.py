import uuid
from typing import Annotated

from fastapi import APIRouter, Header, Response, status

from app.core.dependencies import CurrentUser, DbSession
from app.src.escrow import services
from app.src.escrow.schemas import FundContractOut, StatementOut

router = APIRouter(tags=["Escrow"])


@router.post("/contracts/{contract_id}/fund", response_model=FundContractOut)
def fund_contract(
    contract_id: uuid.UUID,
    session: DbSession,
    user: CurrentUser,
    response: Response,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
) -> FundContractOut:
    result, is_replay = services.fund_contract(session, user, contract_id, idempotency_key)
    response.status_code = status.HTTP_200_OK if is_replay else status.HTTP_201_CREATED
    return result


@router.get("/contracts/{contract_id}/statement", response_model=StatementOut)
def get_statement(contract_id: uuid.UUID, session: DbSession, user: CurrentUser) -> StatementOut:
    return services.get_statement(session, user, contract_id)