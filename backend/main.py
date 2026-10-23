from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

import config
from api.auth import router as auth_router
from api.forms import router as forms_router
from api.insights import router as insights_router
from api.meta import router as meta_router
from api.uploads import router as uploads_router
from container import Container, build_container
from services import auth_service

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s [%(name)s] %(message)s")

# Reachable without logging in: the health check (load balancer) and the login steps themselves.
_PUBLIC_PATHS = {f"{config.API_PREFIX}{path}" for path in ("/health", "/auth/status", "/auth/request-code", "/auth/verify", "/auth/logout")}


def create_app(container: Container | None = None) -> FastAPI:
    """The API with its components (default: built from the configuration)."""
    container = container or build_container(config)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        if container.worker_enabled:
            container.queue.start()
        yield
        container.queue.stop()

    app = FastAPI(title="Document Intake API", lifespan=lifespan)
    app.state.container = container
    app.add_middleware(
        CORSMiddleware,
        allow_origins=config.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    for router in (auth_router, meta_router, uploads_router, forms_router, insights_router):
        app.include_router(router, prefix=config.API_PREFIX)

    @app.middleware("http")
    async def require_login(request: Request, call_next):
        if config.AUTH_ENABLED and request.url.path not in _PUBLIC_PATHS:
            if not auth_service.session_is_valid(request.cookies.get(config.AUTH_COOKIE_NAME)):
                return JSONResponse({"detail": "נדרשת התחברות"}, status_code=401)
        return await call_next(request)

    @app.get(f"{config.API_PREFIX}/health")
    def health_check() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
