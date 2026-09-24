from fastapi import APIRouter, Request, status

from app.core.dependencies import CurrentUser, DbSession
from app.core.rate_limit import limiter
from app.src.accounts import services, utils
from app.src.accounts.schemas import FreelancerOut, LoginIn, RefreshIn, RegisterIn, TokenOut

router = APIRouter(tags=["Authentication"])


@router.post(
    "/auth/register",
    response_model=TokenOut,
    status_code=status.HTTP_201_CREATED,
    summary="Register (anyone)",
)
def register(data: RegisterIn, session: DbSession) -> TokenOut:
    return services.register_user(session, data)


@router.post("/auth/login", response_model=TokenOut, summary="Login (anyone)")
@limiter.limit("5/minute")
def login(request: Request, data: LoginIn, session: DbSession) -> TokenOut:
    return services.authenticate_user(session, data)


@router.post(
    "/auth/refresh",
    response_model=TokenOut,
    summary="Refresh token (anyone with a valid refresh token)",
)
def refresh(data: RefreshIn, session: DbSession) -> TokenOut:
    return services.refresh_access_token(session, data.refresh_token)


@router.get(
    "/freelancers",
    response_model=list[FreelancerOut],
    summary="List freelancers (any authenticated user)",
)
def list_freelancers(session: DbSession, user: CurrentUser) -> list[FreelancerOut]:
    
    freelancers = utils.list_freelancers(session)
    return [FreelancerOut.model_validate(f) for f in freelancers]