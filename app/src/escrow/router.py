import uuid
from typing import Annotated

from fastapi import APIRouter, Header, Response, status

from app.core.dependencies import CurrentUser, DbSession
from app.src.escrow import services
from app.src.escrow.schemas import FundContractOut, StatementOut

router = APIRouter(tags=["Escrow"])



@router.get(
    "/contracts/{contract_id}/statement",
    response_model=StatementOut,
    summary="Get contract statement (party or arbiter)",
)
def get_statement(contract_id: uuid.UUID, session: DbSession, user: CurrentUser) -> StatementOut:
    """200 on success. 403 if the caller isn't a party or an arbiter, 404 if not found."""
    return services.get_statement(session, user, contract_id)