
from fastapi import APIRouter, Request, status

from app.core.dependencies import DbSession
from app.core.rate_limit import limiter
from app.src.accounts import services
from app.src.accounts.schemas import LoginIn, RefreshIn, RegisterIn, TokenOut

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post("/register", response_model=TokenOut, status_code=status.HTTP_201_CREATED)
def register(data: RegisterIn, session: DbSession) -> TokenOut:
    return services.register_user(session, data)

@router.post("/login", response_model=TokenOut)
@limiter.limit("5/minute")
def login(request: Request, data: LoginIn, session: DbSession) -> TokenOut:
    return services.authenticate_user(session, data)

@router.post("/refresh", response_model=TokenOut)
def refresh(data: RefreshIn, session: DbSession) -> TokenOut:
    return services.refresh_access_token(session, data.refresh_token)



