from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel

import config
from services import auth_service

router = APIRouter(prefix="/auth", tags=["auth"])


class CodeRequest(BaseModel):
    email: str | None = None  # typed on the login screen (demo mode); otherwise the code goes to config.AUTH_EMAIL


class VerifyRequest(BaseModel):
    code: str


@router.get("/status")
def auth_status(request: Request):
    """Whether login is required and whether this browser is logged in (also answered when it isn't).
    ask_email: the login screen asks for an address (demo mode) instead of using the lab's mailbox."""
    logged_in = auth_service.session_is_valid(request.cookies.get(config.AUTH_COOKIE_NAME))
    return {
        "enabled": config.AUTH_ENABLED,
        "authenticated": logged_in or not config.AUTH_ENABLED,
        "email": auth_service.masked_email(),
        "ask_email": bool(config.AUTH_DEMO_CODE),
    }


@router.post("/request-code")
def request_code(payload: CodeRequest | None = None):
    try:
        sent_to = auth_service.request_code(payload.email if payload else None)
    except auth_service.AuthNotConfiguredError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except auth_service.AuthError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"email": sent_to}


@router.post("/verify")
def verify(payload: VerifyRequest, response: Response):
    try:
        token = auth_service.verify_code(payload.code)
    except auth_service.AuthError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    response.set_cookie(
        config.AUTH_COOKIE_NAME, token, max_age=config.AUTH_SESSION_HOURS * 3600,
        httponly=True, samesite="strict", secure=config.AUTH_COOKIE_SECURE, path="/",
    )
    return {"authenticated": True}


@router.post("/logout")
def logout(response: Response):
    response.delete_cookie(config.AUTH_COOKIE_NAME, path="/")
    return {"authenticated": False}
