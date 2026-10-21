from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

import config
from api.forms import router as forms_router
from api.meta import router as meta_router
from api.uploads import router as uploads_router
from services.extraction_queue import extraction_queue

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s [%(name)s] %(message)s")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    if config.WORKER_ENABLED:
        extraction_queue.start()
    yield
    extraction_queue.stop()


app = FastAPI(title="Document Intake API", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

for router in (meta_router, uploads_router, forms_router):
    app.include_router(router, prefix=config.API_PREFIX)


@app.get(f"{config.API_PREFIX}/health")
def health_check() -> dict[str, str]:
    return {"status": "ok"}
