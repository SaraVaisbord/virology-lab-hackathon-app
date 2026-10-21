"""Single source of runtime configuration. Every value can be overridden via environment / backend/.env."""

from __future__ import annotations

import os
import re
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
# The test suite sets APP_ENV=test so real secrets from .env are never loaded (or printed) by tests.
if os.getenv("APP_ENV") != "test":
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
# Database: SQLite in DATA_DIR by default; on AWS a separate PostgreSQL server (RDS), e.g.
# DATABASE_URL=postgresql+psycopg://user:password@host:5432/dbname
DATABASE_URL = os.getenv("DATABASE_URL") or f"sqlite:///{(DATA_DIR / 'app.db').as_posix()}"
# Files (uploads, page images) — see storage.py. "local" = DATA_DIR; "s3" = private bucket S3_BUCKET.
STORAGE_BACKEND = os.getenv("STORAGE_BACKEND", "local").strip().lower()
S3_BUCKET = os.getenv("S3_BUCKET", "")
S3_PREFIX = os.getenv("S3_PREFIX", "")
AWS_REGION = os.getenv("AWS_REGION", "")
# Path prefix of every API route: "" locally; "/api" behind the AWS load balancer (/ → frontend, /api → backend).
API_PREFIX = os.getenv("API_PREFIX", "").rstrip("/")

# ── Uploads & page rendering ─────────────────────────────────────────────────
MAX_FILE_SIZE_MB = _env_int("MAX_FILE_SIZE_MB", 50)
MAX_FILE_SIZE = MAX_FILE_SIZE_MB * 1024 * 1024
# Pages are stored at this resolution (scans embedded in PDFs are taken as-is when they are close to it).
# 300 dpi is what OCR needs; the old 200 dpi + 2000 px cap left only ~171 dpi on A4.
PAGE_RENDER_DPI = _env_int("PAGE_RENDER_DPI", 300)
PAGE_MAX_SIDE_PX = _env_int("PAGE_MAX_SIDE_PX", 3600)  # A4 at 300 dpi is 3508 px high
# Pages of one upload straightened in parallel (each needs a full-resolution image in memory).
UPLOAD_PAGE_WORKERS = _env_int("UPLOAD_PAGE_WORKERS", 4)

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

# ── OCR (Tesseract) ──────────────────────────────────────────────────────────
# Tesseract on Windows can't read non-ASCII paths, so the models must live under an ASCII path
# (the project folder name is Hebrew). heb + eng + osd .traineddata files are expected there.
TESSERACT_CMD = os.getenv("TESSERACT_CMD", r"C:\Program Files\Tesseract-OCR\tesseract.exe")
OCR_TESSDATA_DIR = os.getenv("OCR_TESSDATA_DIR", str(Path.home() / "tessdata"))
OCR_LANGUAGES = os.getenv("OCR_LANGUAGES", "heb+eng")
OCR_TIMEOUT_SECONDS = _env_int("OCR_TIMEOUT_SECONDS", 60)

# Handwritten digits: MNIST CNN (ONNX model zoo, MIT licence, ~26 KB) run with OpenCV — see handwriting_digits.py.
HANDWRITTEN_DIGITS_MODEL = Path(os.getenv("HANDWRITTEN_DIGITS_MODEL", str(BASE_DIR / "models" / "mnist-12.onnx")))

# ── Field validation ─────────────────────────────────────────────────────────
# A received date further than this from today is suspicious (e.g. a handwritten 6 read as 0).
RECEIVED_DATE_MAX_AGE_DAYS = _env_int("RECEIVED_DATE_MAX_AGE_DAYS", 365)

# ── Extraction queue ─────────────────────────────────────────────────────────
WORKER_ENABLED = _env_bool("WORKER_ENABLED", True)
# With LLM_ENABLED=false the queue still runs the free local stages (preprocessing, barcodes, OCR) — no tokens.
LLM_ENABLED = _env_bool("LLM_ENABLED", True)
# OCR-only values below this Tesseract confidence (0..100) are marked uncertain.
LOCAL_OCR_MIN_CONFIDENCE = _env_int("LOCAL_OCR_MIN_CONFIDENCE", 60)
WORKER_CONCURRENCY = _env_int("WORKER_CONCURRENCY", 2)
WORKER_IDLE_POLL_SECONDS = _env_int("WORKER_IDLE_POLL_SECONDS", 5)

# ── Gemini ───────────────────────────────────────────────────────────────────
def _env_list(name: str) -> list[str]:
    return [item.strip() for item in os.getenv(name, "").split(",") if item.strip()]


_PLACEHOLDER_KEY = "your-key-here"
_NUMBERED_KEY = re.compile(r"^GEMINI_API_KEY_(\d+)$")


def _gemini_keys() -> list[str]:
    """Several keys (ideally from different Google Cloud projects — quota is per project) are tried in turn.
    Accepted forms, in this order: GEMINI_API_KEY, GEMINI_API_KEY_2, GEMINI_API_KEY_3, ... (numeric order),
    then GEMINI_API_KEYS=key,key,... Duplicates and the .env.example placeholder are dropped."""
    numbered = sorted((int(m.group(1)), value) for name, value in os.environ.items() if (m := _NUMBERED_KEY.match(name)))
    candidates = [os.getenv("GEMINI_API_KEY", ""), *(value for _, value in numbered), *_env_list("GEMINI_API_KEYS")]
    return [key for key in dict.fromkeys(k.strip() for k in candidates) if key and key != _PLACEHOLDER_KEY]


GEMINI_API_KEYS = _gemini_keys()
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "models/gemini-flash-latest")
# Models to fall back to when the primary one is overloaded (503/504) or out of quota, in order.
GEMINI_FALLBACK_MODELS = _env_list("GEMINI_FALLBACK_MODELS")
GEMINI_MODELS = list(dict.fromkeys([GEMINI_MODEL, *GEMINI_FALLBACK_MODELS]))
GEMINI_TIMEOUT_SECONDS = _env_int("GEMINI_TIMEOUT_SECONDS", 120)
GEMINI_MAX_ATTEMPTS = _env_int("GEMINI_MAX_ATTEMPTS", 2)
# How long a key+model route rests after a failure before it is tried again:
GEMINI_QUOTA_DEFAULT_BACKOFF_SECONDS = _env_int("GEMINI_QUOTA_DEFAULT_BACKOFF_SECONDS", 60)  # 429 without a retry time
GEMINI_BUSY_COOLDOWN_SECONDS = _env_int("GEMINI_BUSY_COOLDOWN_SECONDS", 90)  # 500/503/504/timeout (model overloaded)
GEMINI_INVALID_KEY_COOLDOWN_SECONDS = _env_int("GEMINI_INVALID_KEY_COOLDOWN_SECONDS", 3600)  # 400/401/403 key rejected
GEMINI_IMAGE_MAX_SIDE_PX = _env_int("GEMINI_IMAGE_MAX_SIDE_PX", 1600)
GEMINI_IMAGE_JPEG_QUALITY = _env_int("GEMINI_IMAGE_JPEG_QUALITY", 80)
# ── OpenAI (used for provider comparison: compare_providers.py) ─────────────
OPENAI_API_KEY = (os.getenv("OPENAI_API_KEY") or os.getenv("OPEN_AI_API_KEY") or "").strip()  # either spelling
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-5.4-mini")  # same tier as Gemini Flash, for a fair comparison
OPENAI_API_URL = os.getenv("OPENAI_API_URL", "https://api.openai.com/v1/chat/completions")
OPENAI_TIMEOUT_SECONDS = _env_int("OPENAI_TIMEOUT_SECONDS", 180)

# MVP workaround for a local CA-certificate issue (Python 3.14 / Windows), used for Gemini and OpenAI calls.
# Turn off in production.
GEMINI_INSECURE_SSL = _env_bool("GEMINI_INSECURE_SSL", True)
PROMPTS_DIR = BASE_DIR / "prompts"
EXTRACTION_PROMPT_FILE = PROMPTS_DIR / os.getenv("EXTRACTION_PROMPT_FILE", "extraction_prompt.md")
