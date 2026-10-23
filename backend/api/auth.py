from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel

from api.dependencies import get_container
from container import Container
from services.auth_service import AuthError, AuthNotConfiguredError

router = APIRouter(prefix="/auth", tags=["auth"])


class CodeRequest(BaseModel):
    email: str | None = None  # typed on the login screen (demo mode); otherwise the code goes to the lab's mailbox


class VerifyRequest(BaseModel):
    code: str


@router.get("/status")
def auth_status(request: Request, container: Container = Depends(get_container)):
    """Whether login is required and whether this browser is logged in (also answered when it isn't).
    ask_email: the login screen asks for an address (demo mode) instead of using the lab's mailbox."""
    settings, auth = container.settings, container.auth
    logged_in = auth.session_is_valid(request.cookies.get(settings.auth_cookie_name))
    return {
        "enabled": settings.auth_enabled,
        "authenticated": logged_in or not settings.auth_enabled,
        "email": auth.masked_email(),
        "ask_email": bool(settings.auth_demo_code),
    }


@router.post("/request-code")
def request_code(payload: CodeRequest | None = None, container: Container = Depends(get_container)):
    try:
        sent_to = container.auth.request_code(payload.email if payload else None)
    except AuthNotConfiguredError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except AuthError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"email": sent_to}


@router.post("/verify")
def verify(payload: VerifyRequest, response: Response, container: Container = Depends(get_container)):
    settings = container.settings
    try:
        token = container.auth.verify_code(payload.code)
    except AuthError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    response.set_cookie(
        settings.auth_cookie_name, token, max_age=settings.auth_session_hours * 3600,
        httponly=True, samesite="strict", secure=settings.auth_cookie_secure, path="/",
    )
    return {"authenticated": True}


@router.post("/logout")
def logout(response: Response, container: Container = Depends(get_container)):
    response.delete_cookie(container.settings.auth_cookie_name, path="/")
    return {"authenticated": False}
