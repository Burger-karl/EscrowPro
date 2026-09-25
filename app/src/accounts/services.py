from sqlmodel import Session

from app.core.errors import ConflictError, UnauthorizedError
from app.core.security import (
    TokenType, create_access_token,
    create_refresh_token, decode_token, 
    hash_password, verify_password
)
from app.src.accounts import utils
from app.src.accounts.models import User, UserRole
from app.src.accounts.schemas import AdminUserCreateIn, LoginIn, RegisterIn, TokenOut, UserOut


def issue_tokens(user: User) -> TokenOut:
    return TokenOut(
        access_token=create_access_token(str(user.id), user.role.value),
        refresh_token=create_refresh_token(str(user.id)),
        user=UserOut.model_validate(user),
    )


def register_user(session: Session, data: RegisterIn) -> TokenOut:
    if utils.get_user_by_email(session, data.email) is not None:
        raise ConflictError("an account with this email already exists", code="email_taken")

    user = User(
        email=data.email,
        password_hash=hash_password(data.password),
        full_name=data.full_name,
        role=data.role,
    )
    user = utils.create_user(session, user)
    return issue_tokens(user)


def authenticate_user(session: Session, data: LoginIn) -> TokenOut:
    user = utils.get_user_by_email(session, data.email)
    if user is None or not verify_password(data.password, user.password_hash):
        raise UnauthorizedError("invalid email or password", code="invalid credentials")
    if not user.is_active:
        raise UnauthorizedError("this account is disabled", code="account_disabled")

    return issue_tokens(user)


def refresh_access_token(session: Session, refresh_token: str) -> TokenOut:
    from app.core.security import TokenPayloadError

    try:
        payload = decode_token(refresh_token, expected_type=TokenType.REFRESH)
    except TokenPayloadError as exc:
        raise UnauthorizedError(str(exc), code="invalid_refresh_token") from exc

    import uuid

    user = utils.get_user_by_id(session, uuid.UUID(payload["sub"]))
    if user is None or not user.is_active:
        raise UnauthorizedError("account no longer valid", code="account_disabled")

    return issue_tokens(user)


def create_user_by_admin(session: Session, admin_user: User, data: AdminUserCreateIn) -> UserOut:
    from app.core.errors import ForbiddenError

    if admin_user.role != UserRole.ADMIN:
        raise ForbiddenError("only administrators can create accounts with arbitrary roles", code="role_not_allowed")

    if utils.get_user_by_email(session, data.email) is not None:
        raise ConflictError("an account with this email already exists", code="email_taken")

    user = User(
        email=data.email,
        password_hash=hash_password(data.password),
        full_name=data.full_name,
        role=data.role,
    )
    user = utils.create_user(session, user)
    return UserOut.model_validate(user)


def list_freelancers(session: Session) -> list[User]:
    return utils.list_freelancers(session)
