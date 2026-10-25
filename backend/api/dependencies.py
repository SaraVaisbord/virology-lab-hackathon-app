"""FastAPI dependencies: the components built by the composition root (container.py), stored on the app."""

from __future__ import annotations

from fastapi import Depends, Request

from config import Settings
from container import Container


def get_container(request: Request) -> Container:
    return request.app.state.container


def get_settings(container: Container = Depends(get_container)) -> Settings:
    return container.settings
