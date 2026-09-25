from fastapi import APIRouter, Request, status

from app.core.dependencies import CurrentUser, DbSession
from app.core.rate_limit import limiter
from app.src.accounts import services
from app.src.accounts.schemas import (
    AdminUserCreateIn,
    FreelancerOut,
    LoginIn,
    RefreshIn,
    RegisterIn,
    TokenOut,
    UserOut,
)

router = APIRouter(tags=["Authentication"])


@router.post(
    "/auth/register",
    response_model=TokenOut,
    status_code=status.HTTP_201_CREATED,
    summary="[Role: Public] Register account",
    description="Registers a new client or freelancer account and returns access and refresh JWT tokens. Role must be 'client' or 'freelancer'. Accessible by: Public (anyone).",
)
def register(data: RegisterIn, session: DbSession) -> TokenOut:
    return services.register_user(session, data)


@router.post(
    "/auth/users",
    response_model=UserOut,
    status_code=status.HTTP_201_CREATED,
    summary="[Role: Admin] Create user with any role",
    description="Allows administrators to provision users with any role (client, freelancer, arbiter, finance, admin). Accessible by: Admin only.",
)
def create_user_by_admin(data: AdminUserCreateIn, session: DbSession, user: CurrentUser) -> UserOut:
    return services.create_user_by_admin(session, user, data)


@router.post(
    "/auth/login",
    response_model=TokenOut,
    summary="[Role: Public] User login",
    description="Authenticates email and password credentials and issues JWT access and refresh tokens. Rate-limited to 5/minute. Accessible by: Public (anyone).",
)
@limiter.limit("5/minute")
def login(request: Request, data: LoginIn, session: DbSession) -> TokenOut:
    return services.authenticate_user(session, data)


@router.post(
    "/auth/refresh",
    response_model=TokenOut,
    summary="[Role: Public with refresh token] Refresh access token",
    description="Exchanges a valid refresh token for a newly issued access token. Accessible by: Anyone with a valid refresh token.",
)
def refresh(data: RefreshIn, session: DbSession) -> TokenOut:
    return services.refresh_access_token(session, data.refresh_token)


@router.get(
    "/freelancers",
    response_model=list[FreelancerOut],
    summary="[Role: Authenticated] List freelancers",
    description="Returns a list of all active registered freelancers available to be assigned to contracts. Accessible by: Any authenticated user.",
)
def list_freelancers(session: DbSession, user: CurrentUser) -> list[FreelancerOut]:
    freelancers = services.list_freelancers(session)
    return [FreelancerOut.model_validate(f) for f in freelancers]