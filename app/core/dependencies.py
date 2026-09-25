import uuid
from collections.abc import Callable
from typing import Annotated

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlmodel import Session

from app.core.errors import ForbiddenError, UnauthorizedError
from app.core.security import TokenPayloadError, TokenType, decode_token
from app.db.session import get_session
from app.src.accounts import utils
from app.src.accounts.models import User, UserRole


bearer_scheme = HTTPBearer()

# DB
def get_db() -> Session:
    yield from get_session()

DbSession = Annotated[Session, Depends(get_db)]


# Auth
def get_current_user(
    session: DbSession, 
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(bearer_scheme)],
) -> User:
    token = credentials.credentials
    try:
        payload = decode_token(token, expected_type=TokenType.ACCESS)
    except TokenPayloadError as exc:
        raise UnauthorizedError(str(exc), code="invalid_token") from exc

    try:
        user_id = uuid.UUID(payload["sub"])
    except (KeyError, ValueError) as exc:
        raise UnauthorizedError("malformed token subject", code="invalid_token") from exc

    user = utils.get_user_by_id(session, user_id)
    if user is None or not user.is_active:
        raise UnauthorizedError("account no longer valid", code="account_disabled")

    return user


CurrentUser = Annotated[User, Depends(get_current_user)]

def require_role(*allowed_roles: UserRole) -> Callable[[CurrentUser], User]:
    def _check(user: CurrentUser) -> User:
        if user.role != UserRole.ADMIN and user.role not in allowed_roles:
            raise ForbiddenError(
                f"this action requires one of: {', '.join(r.value for r in allowed_roles)}",
                code="role_not_allowed",
            )
        return user

    return _check




