from __future__ import annotations

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.forms import router as forms_router
from api.uploads import router as uploads_router

CORS_ORIGINS = [
    origin.strip()
    for origin in os.getenv(
        "CORS_ORIGINS",
        "http://localhost:5173,http://localhost:5176,http://127.0.0.1:5173,http://127.0.0.1:5176",
    ).split(",")
    if origin.strip()
]

app = FastAPI(title="Document Intake API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(uploads_router)
app.include_router(forms_router)


@app.get("/health")
def health_check() -> dict[str, str]:
    return {"status": "ok"}
