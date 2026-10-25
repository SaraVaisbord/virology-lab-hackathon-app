"""Server entry point (uvicorn main:app): the application built from the environment's settings."""

from __future__ import annotations

import logging

from api.app import create_app

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s [%(name)s] %(message)s")

app = create_app()
