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

# ── Login: a one-time code sent to one mailbox ───────────────────────────────
# Whoever can read AUTH_EMAIL can log in: "send code" mails a 6-digit code there; entering it gives a signed session
# cookie. Off when AUTH_ENABLED=false (local development, tests).
AUTH_ENABLED = _env_bool("AUTH_ENABLED", True)
# DEMO ONLY: when set, "send code" sends nothing and this fixed code always logs in (any email address may be typed).
# For showing the login flow before mail sending is set up — remove it before real data.
AUTH_DEMO_CODE = os.getenv("AUTH_DEMO_CODE", "").strip()
AUTH_EMAIL = os.getenv("AUTH_EMAIL", "").strip()
SMTP_HOST = os.getenv("SMTP_HOST", "").strip()
SMTP_PORT = _env_int("SMTP_PORT", 587)  # 587 = STARTTLS, 465 = TLS from the start
SMTP_USERNAME = os.getenv("SMTP_USERNAME", "").strip()
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "").strip()
SMTP_FROM = os.getenv("SMTP_FROM", "").strip() or SMTP_USERNAME
SMTP_TIMEOUT_SECONDS = _env_int("SMTP_TIMEOUT_SECONDS", 20)
# Signs the session cookie. Set it (a long random string) so sessions survive a restart; empty → a random one per run.
AUTH_SECRET = os.getenv("AUTH_SECRET", "").strip()
AUTH_CODE_TTL_MINUTES = _env_int("AUTH_CODE_TTL_MINUTES", 10)
AUTH_CODE_MAX_ATTEMPTS = _env_int("AUTH_CODE_MAX_ATTEMPTS", 5)  # wrong guesses before the code is void
AUTH_CODE_RESEND_SECONDS = _env_int("AUTH_CODE_RESEND_SECONDS", 60)  # at most one code per this many seconds
AUTH_SESSION_HOURS = _env_int("AUTH_SESSION_HOURS", 12)
AUTH_COOKIE_NAME = "session"
# Send the cookie over HTTPS only. Keep false while the site is plain HTTP (it would never be sent back).
AUTH_COOKIE_SECURE = _env_bool("AUTH_COOKIE_SECURE", False)

# ── Correction insights (patterns in the lab worker's corrections) ───────────
# Below this many reviewed machine values in the range there is not enough history to point at any pattern.
INSIGHTS_MIN_REVIEWED_FIELDS = _env_int("INSIGHTS_MIN_REVIEWED_FIELDS", 20)
# A pattern is reported from this many events; from the next two counts its support is medium / high.
INSIGHTS_MIN_EVENTS = _env_int("INSIGHTS_MIN_EVENTS", 3)
INSIGHTS_MEDIUM_SUPPORT_EVENTS = _env_int("INSIGHTS_MEDIUM_SUPPORT_EVENTS", 10)
INSIGHTS_HIGH_SUPPORT_EVENTS = _env_int("INSIGHTS_HIGH_SUPPORT_EVENTS", 30)
# A field is "often corrected" when at least this share (%) of its reviewed values were corrected.
INSIGHTS_MIN_CORRECTION_PERCENT = _env_int("INSIGHTS_MIN_CORRECTION_PERCENT", 20)
# A pattern is "concentrated" in a form type / sender / way of writing when at least this share (%) of it is there.
INSIGHTS_CONCENTRATION_PERCENT = _env_int("INSIGHTS_CONCENTRATION_PERCENT", 80)

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


def _api_keys(name: str) -> list[str]:
    """Several keys of one provider, tried in turn. Accepted forms, in this order: NAME, NAME_2, NAME_3, ...
    (numeric order), then NAMES=key,key,... Duplicates and the .env.example placeholder are dropped."""
    numbered_name = re.compile(rf"^{name}_(\d+)$")
    numbered = sorted((int(m.group(1)), value) for env, value in os.environ.items() if (m := numbered_name.match(env)))
    candidates = [os.getenv(name, ""), *(value for _, value in numbered), *_env_list(f"{name}S")]
    return [key for key in dict.fromkeys(k.strip() for k in candidates) if key and key != _PLACEHOLDER_KEY]


# Quota is per Google Cloud project: keys from different projects add up, keys of one project share it.
GEMINI_API_KEYS = _api_keys("GEMINI_API_KEY")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "models/gemini-flash-latest")
# Models to fall back to when the primary one is overloaded (503/504) or out of quota, in order. Each model has its
# own daily quota. flash-lite is weaker (more extra/missed values — those are never "verified" and go to review).
GEMINI_FALLBACK_MODELS = _env_list("GEMINI_FALLBACK_MODELS") or ["models/gemini-3.5-flash-lite"]
GEMINI_MODELS = list(dict.fromkeys([GEMINI_MODEL, *GEMINI_FALLBACK_MODELS]))
GEMINI_TIMEOUT_SECONDS = _env_int("GEMINI_TIMEOUT_SECONDS", 120)
GEMINI_MAX_ATTEMPTS = _env_int("GEMINI_MAX_ATTEMPTS", 2)
# How long a key+model route rests after a failure before it is tried again:
GEMINI_QUOTA_DEFAULT_BACKOFF_SECONDS = _env_int("GEMINI_QUOTA_DEFAULT_BACKOFF_SECONDS", 60)  # 429 without a retry time
GEMINI_BUSY_COOLDOWN_SECONDS = _env_int("GEMINI_BUSY_COOLDOWN_SECONDS", 90)  # 500/503/504/timeout (model overloaded)
GEMINI_INVALID_KEY_COOLDOWN_SECONDS = _env_int("GEMINI_INVALID_KEY_COOLDOWN_SECONDS", 3600)  # 400/401/403 key rejected
GEMINI_IMAGE_MAX_SIDE_PX = _env_int("GEMINI_IMAGE_MAX_SIDE_PX", 1600)
GEMINI_IMAGE_JPEG_QUALITY = _env_int("GEMINI_IMAGE_JPEG_QUALITY", 80)

# ── LLM providers: which ones read the page, in order ────────────────────────
# The first provider that answers is used; one that is out of quota, overloaded or not configured hands the page to
# the next (services/llm_router.py). Known providers: gemini, claude, openai.
LLM_PROVIDERS = _env_list("LLM_PROVIDERS") or ["gemini", "claude"]

# ── Claude (Anthropic) ───────────────────────────────────────────────────────
# ANTHROPIC_API_KEY, ANTHROPIC_API_KEY_2, ... — tried in turn. Rate limits are per Anthropic organization: keys of
# one organization share them, so only keys from different organizations add capacity.
ANTHROPIC_API_KEYS = _api_keys("ANTHROPIC_API_KEY")
CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "claude-opus-5-5")
# Thinking depth (low / medium / high / xhigh / max). Set explicitly: the model's own default is "medium".
CLAUDE_EFFORT = os.getenv("CLAUDE_EFFORT", "medium")
CLAUDE_MAX_TOKENS = _env_int("CLAUDE_MAX_TOKENS", 16000)
CLAUDE_TIMEOUT_SECONDS = _env_int("CLAUDE_TIMEOUT_SECONDS", 180)
# How long Claude rests after a failure before it is tried again (as for Gemini routes):
CLAUDE_QUOTA_DEFAULT_BACKOFF_SECONDS = _env_int("CLAUDE_QUOTA_DEFAULT_BACKOFF_SECONDS", 60)  # 429 without retry-after
CLAUDE_BUSY_COOLDOWN_SECONDS = _env_int("CLAUDE_BUSY_COOLDOWN_SECONDS", 90)  # overloaded / 5xx / timeout / network
CLAUDE_INVALID_KEY_COOLDOWN_SECONDS = _env_int("CLAUDE_INVALID_KEY_COOLDOWN_SECONDS", 3600)  # 401/403 key rejected

# ── OpenAI (used for provider comparison: scripts/compare_providers.py) ─────────────
OPENAI_API_KEY = (os.getenv("OPENAI_API_KEY") or os.getenv("OPEN_AI_API_KEY") or "").strip()  # either spelling
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-5.4-mini")  # same tier as Gemini Flash, for a fair comparison
OPENAI_API_URL = os.getenv("OPENAI_API_URL", "https://api.openai.com/v1/chat/completions")
OPENAI_TIMEOUT_SECONDS = _env_int("OPENAI_TIMEOUT_SECONDS", 180)

# MVP workaround for a local CA-certificate issue (Python 3.14 / Windows), used for Gemini, Claude and OpenAI calls.
# Turn off in production.
GEMINI_INSECURE_SSL = _env_bool("GEMINI_INSECURE_SSL", True)
PROMPTS_DIR = BASE_DIR / "prompts"
EXTRACTION_PROMPT_FILE = PROMPTS_DIR / os.getenv("EXTRACTION_PROMPT_FILE", "extraction_prompt.md")
