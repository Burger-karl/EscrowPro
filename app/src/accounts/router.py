
# from fastapi import APIRouter, Request, status

# from app.core.dependencies import DbSession
# from app.core.rate_limit import limiter
# from app.src.accounts import services
# from app.src.accounts.schemas import LoginIn, RefreshIn, RegisterIn, TokenOut

# router = APIRouter(prefix="/auth", tags=["Authentication"])


# @router.post("/register", response_model=TokenOut, status_code=status.HTTP_201_CREATED)
# def register(data: RegisterIn, session: DbSession) -> TokenOut:
#     return services.register_user(session, data)

# @router.post("/login", response_model=TokenOut)
# @limiter.limit("5/minute")
# def login(request: Request, data: LoginIn, session: DbSession) -> TokenOut:
#     return services.authenticate_user(session, data)

# @router.post("/refresh", response_model=TokenOut)
# def refresh(data: RefreshIn, session: DbSession) -> TokenOut:
#     return services.refresh_access_token(session, data.refresh_token)



from fastapi import APIRouter, Request, status

from app.core.dependencies import DbSession
from app.core.rate_limit import limiter
from app.src.accounts import services
from app.src.accounts.schemas import LoginIn, RefreshIn, RegisterIn, TokenOut

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post(
    "/register",
    response_model=TokenOut,
    status_code=status.HTTP_201_CREATED,
    summary="Register (public)",
)
def register(data: RegisterIn, session: DbSession) -> TokenOut:
    """201 on success, 409 if the email is taken, 422 on bad input."""
    return services.register_user(session, data)


@router.post("/login", response_model=TokenOut, summary="Login (public)")
@limiter.limit("5/minute")
def login(request: Request, data: LoginIn, session: DbSession) -> TokenOut:
    """200 on success, 401 on bad credentials. Rate-limited: 5/min per IP."""
    return services.authenticate_user(session, data)


@router.post("/refresh", response_model=TokenOut, summary="Refresh token (anyone with a valid refresh token)")
def refresh(data: RefreshIn, session: DbSession) -> TokenOut:
    """Exchange a valid refresh token for a fresh access/refresh pair."""
    return services.refresh_access_token(session, data.refresh_token)