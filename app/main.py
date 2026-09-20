"""
FastAPI app, router includes, middleware, lifespan.

Only auth is wired up so far (accounts domain). As contracts, escrow,
disputes, payouts, and payments land, include their routers below in
the same pattern.
"""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from app.core.config import settings
from app.core.errors import register_exception_handlers
from app.core.middleware import RequestContextMiddleware
from app.core.rate_limit import limiter

from app.src.accounts.router import router as accounts_router
from app.src.contracts.router import router as contracts_router


logging.basicConfig(level=settings.LOG_LEVEL)

API_PREFIX = "/api/v1"


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: nothing yet — Firestore client, Redis pool, etc. will
    # be initialized here as those domains are built.
    yield
    # Shutdown: close pooled clients here.


def create_app() -> FastAPI:
    app = FastAPI(
        title="PayWork API",
        description="Freelance escrow backend — holds client funds until "
        "milestone work is approved.",
        version="0.1.0",
        lifespan=lifespan,
    )

    # --- Middleware ---
    app.add_middleware(RequestContextMiddleware)
    app.state.limiter = limiter
    app.add_middleware(SlowAPIMiddleware)
    app.add_exception_handler(RateLimitExceeded, lambda r, e: _rate_limit_handler(r, e))

    # --- Error handling ---
    register_exception_handlers(app)

    # --- Routers ---
    app.include_router(accounts_router, prefix=API_PREFIX)
    app.include_router(contracts_router, prefix=API_PREFIX)
    # app.include_router(escrow_router, prefix=API_PREFIX)
    # app.include_router(disputes_router, prefix=API_PREFIX)
    # app.include_router(payouts_router, prefix=API_PREFIX)
    # app.include_router(payments_router, prefix=API_PREFIX)

    @app.get("/health", tags=["meta"])
    def health() -> dict:
        return {"status": "ok"}

    return app


def _rate_limit_handler(request, exc):
    from fastapi.responses import JSONResponse

    return JSONResponse(
        status_code=429,
        content={"error": {"code": "rate_limited", "message": "too many requests", "request_id": None}},
        headers={"Retry-After": "60"},
    )


app = create_app()
