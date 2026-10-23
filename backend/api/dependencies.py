"""FastAPI dependencies: the components built by the composition root (container.py), stored on the app."""

from __future__ import annotations

from fastapi import Depends, Request

from container import Container
from services.extraction_queue import ExtractionQueue


def get_container(request: Request) -> Container:
    return request.app.state.container


def get_queue(container: Container = Depends(get_container)) -> ExtractionQueue:
    return container.queue
