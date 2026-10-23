"""The FastAPI application: routers, CORS, the login check, and the worker's lifetime."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from api import auth, forms, insights, meta, uploads
from config import Settings, load_settings
from container import Container, build_container

# Reachable without logging in: the health check (load balancer) and the login steps themselves.
_PUBLIC_PATHS = ("/health", "/auth/status", "/auth/request-code", "/auth/verify", "/auth/logout")


def create_app(settings: Settings | None = None, container: Container | None = None) -> FastAPI:
    """The API with its components (default: built from the environment's settings)."""
    container = container or build_container(settings or load_settings())
    settings = container.settings
    public_paths = {f"{settings.api_prefix}{path}" for path in _PUBLIC_PATHS}

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        if settings.worker_enabled:
            container.queue.start()
        yield
        container.queue.stop()

    app = FastAPI(title="Document Intake API", lifespan=lifespan)
    app.state.container = container
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    for router in (auth.router, meta.router, uploads.router, forms.create_router(settings), insights.router):
        app.include_router(router, prefix=settings.api_prefix)

    @app.middleware("http")
    async def require_login(request: Request, call_next):
        if settings.auth_enabled and request.url.path not in public_paths:
            if not container.auth.session_is_valid(request.cookies.get(settings.auth_cookie_name)):
                return JSONResponse({"detail": "נדרשת התחברות"}, status_code=401)
        return await call_next(request)

    @app.get(f"{settings.api_prefix}/health")
    def health_check() -> dict[str, str]:
        return {"status": "ok"}

    return app
