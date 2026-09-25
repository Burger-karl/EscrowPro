import uuid

from fastapi import APIRouter, Query

from app.core.dependencies import CurrentUser, DbSession
from app.src.escrow import services
from app.src.escrow.schemas import StatementOut

router = APIRouter(tags=["Escrow"])


@router.get(
    "/contracts/{contract_id}/statement",
    response_model=StatementOut,
    summary="[Role: Client, Freelancer, Arbiter, Admin] Get contract statement",
    description="Returns account balances (escrow balance, freelancer earnings, platform fees) and paginated double-entry ledger movements for a contract. Cached in Redis with cache invalidation on writes. Accessible by: Client (contract owner), Freelancer (assigned), Arbiter, Admin.",
)
def get_statement(
    contract_id: uuid.UUID,
    session: DbSession,
    user: CurrentUser,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> StatementOut:
    """200 on success. 403 if the caller isn't a party or an arbiter, 404 if not found."""
    return services.get_statement(session, user, contract_id, limit=limit, offset=offset)