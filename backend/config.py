"""Single source of runtime configuration. Every value can be overridden via environment / backend/.env."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env", override=False)


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    return int(value) if value else default


# ── Storage ──────────────────────────────────────────────────────────────────
DATA_DIR = Path(os.getenv("APP_DATA_DIR", str(BASE_DIR / "data"))).resolve()
UPLOADS_DIR = DATA_DIR / "uploads"
PAGES_IMG_DIR = DATA_DIR / "pages_img"
DATABASE_URL = os.getenv("DATABASE_URL") or f"sqlite:///{(DATA_DIR / 'app.db').as_posix()}"

# ── Uploads & page rendering ─────────────────────────────────────────────────
MAX_FILE_SIZE_MB = _env_int("MAX_FILE_SIZE_MB", 50)
MAX_FILE_SIZE = MAX_FILE_SIZE_MB * 1024 * 1024
PAGE_RENDER_DPI = _env_int("PAGE_RENDER_DPI", 200)
PAGE_MAX_SIDE_PX = _env_int("PAGE_MAX_SIDE_PX", 2000)

# ── API ──────────────────────────────────────────────────────────────────────
CORS_ORIGINS = [
    origin.strip()
    for origin in os.getenv(
        "CORS_ORIGINS",
        "http://localhost:5173,http://localhost:5176,http://127.0.0.1:5173,http://127.0.0.1:5176",
    ).split(",")
    if origin.strip()
]
DEFAULT_PAGE_SIZE = _env_int("DEFAULT_PAGE_SIZE", 50)
MAX_PAGE_SIZE = _env_int("MAX_PAGE_SIZE", 500)
EXPORT_MAX_ROWS = _env_int("EXPORT_MAX_ROWS", 5000)
# How often the UI polls while forms are still being processed.
PROCESSING_POLL_INTERVAL_MS = _env_int("PROCESSING_POLL_INTERVAL_MS", 3000)

# ── Field validation ─────────────────────────────────────────────────────────
# A received date further than this from today is suspicious (e.g. a handwritten 6 read as 0).
RECEIVED_DATE_MAX_AGE_DAYS = _env_int("RECEIVED_DATE_MAX_AGE_DAYS", 365)

# ── Extraction queue ─────────────────────────────────────────────────────────
WORKER_ENABLED = _env_bool("WORKER_ENABLED", True)
WORKER_CONCURRENCY = _env_int("WORKER_CONCURRENCY", 2)
WORKER_IDLE_POLL_SECONDS = _env_int("WORKER_IDLE_POLL_SECONDS", 5)

# ── Gemini ───────────────────────────────────────────────────────────────────
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "models/gemini-flash-latest")
GEMINI_TIMEOUT_SECONDS = _env_int("GEMINI_TIMEOUT_SECONDS", 120)
GEMINI_MAX_ATTEMPTS = _env_int("GEMINI_MAX_ATTEMPTS", 2)
# Used when a 429 response does not say how long to wait.
GEMINI_QUOTA_DEFAULT_BACKOFF_SECONDS = _env_int("GEMINI_QUOTA_DEFAULT_BACKOFF_SECONDS", 60)
GEMINI_IMAGE_MAX_SIDE_PX = _env_int("GEMINI_IMAGE_MAX_SIDE_PX", 1600)
GEMINI_IMAGE_JPEG_QUALITY = _env_int("GEMINI_IMAGE_JPEG_QUALITY", 80)
# MVP workaround for a local CA-certificate issue (Python 3.14 / Windows). Turn off in production.
GEMINI_INSECURE_SSL = _env_bool("GEMINI_INSECURE_SSL", True)
PROMPTS_DIR = BASE_DIR / "prompts"
EXTRACTION_PROMPT_FILE = PROMPTS_DIR / os.getenv("EXTRACTION_PROMPT_FILE", "extraction_prompt.md")
