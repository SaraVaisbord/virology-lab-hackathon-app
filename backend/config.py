"""Single source of runtime configuration: load_settings() reads every value from the environment / backend/.env
(defaults below) into one immutable Settings object, which the composition root (container.py) hands out."""

from __future__ import annotations

import os
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
_PLACEHOLDER_KEY = "your-key-here"


@dataclass(frozen=True)
class Settings:
    # ── Storage ──────────────────────────────────────────────────────────────
    data_dir: Path
    database_url: str
    storage_backend: str  # "local" = data_dir; "s3" = private bucket s3_bucket (see integrations/storage.py)
    s3_bucket: str
    s3_prefix: str
    aws_region: str
    api_prefix: str  # "" locally; "/api" behind the AWS load balancer (/ → frontend, /api → backend)

    # ── Uploads & page rendering ─────────────────────────────────────────────
    max_file_size_mb: int
    page_render_dpi: int  # pages are stored at this resolution (scans embedded in PDFs taken as-is when close to it)
    page_max_side_px: int
    upload_page_workers: int  # pages of one upload straightened in parallel (each a full-resolution image in memory)

    # ── API ──────────────────────────────────────────────────────────────────
    cors_origins: list[str]
    default_page_size: int
    max_page_size: int
    export_max_rows: int
    processing_poll_interval_ms: int  # how often the UI polls while forms are still being processed

    # ── OCR (Tesseract) ──────────────────────────────────────────────────────
    tesseract_cmd: str
    ocr_tessdata_dir: str
    ocr_languages: str
    ocr_timeout_seconds: int
    handwritten_digits_model: Path

    # ── Field validation ─────────────────────────────────────────────────────
    received_date_max_age_days: int

    # ── Login: a one-time code sent to one mailbox ───────────────────────────
    auth_enabled: bool
    auth_demo_code: str
    auth_email: str
    smtp_host: str
    smtp_port: int
    smtp_username: str
    smtp_password: str
    smtp_from: str
    smtp_timeout_seconds: int
    auth_secret: str
    auth_code_ttl_minutes: int
    auth_code_max_attempts: int
    auth_code_resend_seconds: int
    auth_session_hours: int
    auth_cookie_name: str
    auth_cookie_secure: bool

    # ── Correction insights ──────────────────────────────────────────────────
    insights_min_reviewed_fields: int
    insights_min_events: int
    insights_medium_support_events: int
    insights_high_support_events: int
    insights_min_correction_percent: int
    insights_concentration_percent: int

    # ── Extraction queue ─────────────────────────────────────────────────────
    worker_enabled: bool
    llm_enabled: bool
    local_ocr_min_confidence: int
    worker_concurrency: int
    worker_idle_poll_seconds: int

    # ── LLM providers ────────────────────────────────────────────────────────
    llm_providers: list[str]
    gemini_api_keys: list[str]
    gemini_models: list[str]  # primary first, then the fallbacks
    gemini_timeout_seconds: int
    gemini_max_attempts: int
    gemini_quota_default_backoff_seconds: int
    gemini_busy_cooldown_seconds: int
    gemini_invalid_key_cooldown_seconds: int
    gemini_image_max_side_px: int
    gemini_image_jpeg_quality: int
    anthropic_api_keys: list[str]
    claude_model: str
    claude_effort: str
    claude_max_tokens: int
    claude_timeout_seconds: int
    claude_quota_default_backoff_seconds: int
    claude_busy_cooldown_seconds: int
    claude_invalid_key_cooldown_seconds: int
    openai_api_key: str
    openai_model: str
    openai_api_url: str
    openai_timeout_seconds: int
    llm_insecure_ssl: bool
    extraction_prompt_file: Path

    @property
    def max_file_size(self) -> int:
        return self.max_file_size_mb * 1024 * 1024


class _Env:
    def __init__(self, environ: Mapping[str, str]) -> None:
        self._environ = environ

    def str(self, name: str, default: str = "") -> str:
        return self._environ.get(name, default)

    def stripped(self, name: str) -> str:
        return self._environ.get(name, "").strip()

    def bool(self, name: str, default: bool) -> bool:
        value = self._environ.get(name)
        if value is None:
            return default
        return value.strip().lower() in {"1", "true", "yes", "on"}

    def int(self, name: str, default: int) -> int:
        value = self._environ.get(name)
        return int(value) if value else default

    def list(self, name: str) -> list[str]:
        return [item.strip() for item in self._environ.get(name, "").split(",") if item.strip()]

    def api_keys(self, name: str) -> list[str]:
        """Several keys of one provider, tried in turn. Accepted forms, in this order: NAME, NAME_2, NAME_3, ...
        (numeric order), then NAMES=key,key,... Duplicates and the .env.example placeholder are dropped."""
        numbered_name = re.compile(rf"^{name}_(\d+)$")
        numbered = sorted((int(m.group(1)), value) for env, value in self._environ.items() if (m := numbered_name.match(env)))
        candidates = [self._environ.get(name, ""), *(value for _, value in numbered), *self.list(f"{name}S")]
        return [key for key in dict.fromkeys(k.strip() for k in candidates) if key and key != _PLACEHOLDER_KEY]


def load_settings(environ: Mapping[str, str] | None = None) -> Settings:
    """The settings from `environ` (default: the process environment, after loading backend/.env into it).
    The test suite sets APP_ENV=test so real secrets from .env are never loaded (or printed) by tests."""
    if environ is None:
        if os.getenv("APP_ENV") != "test":
            load_dotenv(BASE_DIR / ".env", override=False)
        environ = os.environ
    env = _Env(environ)

    data_dir = Path(env.str("APP_DATA_DIR", str(BASE_DIR / "data"))).resolve()
    smtp_username = env.stripped("SMTP_USERNAME")
    gemini_model = env.str("GEMINI_MODEL", "models/gemini-flash-latest")
    return Settings(
        data_dir=data_dir,
        # SQLite in data_dir by default; on AWS a separate PostgreSQL server (RDS), e.g.
        # DATABASE_URL=postgresql+psycopg://user:password@host:5432/dbname
        database_url=env.str("DATABASE_URL") or f"sqlite:///{(data_dir / 'app.db').as_posix()}",
        storage_backend=env.str("STORAGE_BACKEND", "local").strip().lower(),
        s3_bucket=env.str("S3_BUCKET"),
        s3_prefix=env.str("S3_PREFIX"),
        aws_region=env.str("AWS_REGION"),
        api_prefix=env.str("API_PREFIX").rstrip("/"),
        max_file_size_mb=env.int("MAX_FILE_SIZE_MB", 50),
        # 300 dpi is what OCR needs; the old 200 dpi + 2000 px cap left only ~171 dpi on A4.
        page_render_dpi=env.int("PAGE_RENDER_DPI", 300),
        page_max_side_px=env.int("PAGE_MAX_SIDE_PX", 3600),  # A4 at 300 dpi is 3508 px high
        upload_page_workers=env.int("UPLOAD_PAGE_WORKERS", 4),
        cors_origins=env.list("CORS_ORIGINS") if "CORS_ORIGINS" in environ else [
            "http://localhost:5173", "http://localhost:5176", "http://127.0.0.1:5173", "http://127.0.0.1:5176"],
        default_page_size=env.int("DEFAULT_PAGE_SIZE", 50),
        max_page_size=env.int("MAX_PAGE_SIZE", 500),
        export_max_rows=env.int("EXPORT_MAX_ROWS", 5000),
        processing_poll_interval_ms=env.int("PROCESSING_POLL_INTERVAL_MS", 3000),
        # Tesseract on Windows can't read non-ASCII paths, so the models must live under an ASCII path
        # (the project folder name is Hebrew). heb + eng + osd .traineddata files are expected there.
        tesseract_cmd=env.str("TESSERACT_CMD", r"C:\Program Files\Tesseract-OCR\tesseract.exe"),
        ocr_tessdata_dir=env.str("OCR_TESSDATA_DIR", str(Path.home() / "tessdata")),
        ocr_languages=env.str("OCR_LANGUAGES", "heb+eng"),
        ocr_timeout_seconds=env.int("OCR_TIMEOUT_SECONDS", 60),
        # Handwritten digits: MNIST CNN (ONNX model zoo, MIT licence, ~26 KB) — see experimental/handwriting_digits.py.
        handwritten_digits_model=Path(env.str("HANDWRITTEN_DIGITS_MODEL", str(BASE_DIR / "models" / "mnist-12.onnx"))),
        # A received date further than this from today is suspicious (e.g. a handwritten 6 read as 0).
        received_date_max_age_days=env.int("RECEIVED_DATE_MAX_AGE_DAYS", 365),
        # Whoever can read AUTH_EMAIL can log in: "send code" mails a 6-digit code there; entering it gives a signed
        # session cookie. Off when AUTH_ENABLED=false (local development, tests).
        auth_enabled=env.bool("AUTH_ENABLED", True),
        # DEMO ONLY: when set, "send code" sends nothing and this fixed code always logs in (any email address may be
        # typed). For showing the login flow before mail sending is set up — remove it before real data.
        auth_demo_code=env.stripped("AUTH_DEMO_CODE"),
        auth_email=env.stripped("AUTH_EMAIL"),
        smtp_host=env.stripped("SMTP_HOST"),
        smtp_port=env.int("SMTP_PORT", 587),  # 587 = STARTTLS, 465 = TLS from the start
        smtp_username=smtp_username,
        smtp_password=env.stripped("SMTP_PASSWORD"),
        smtp_from=env.stripped("SMTP_FROM") or smtp_username,
        smtp_timeout_seconds=env.int("SMTP_TIMEOUT_SECONDS", 20),
        # Signs the session cookie. Set it (a long random string) so sessions survive a restart; empty → a random one
        # per run.
        auth_secret=env.stripped("AUTH_SECRET"),
        auth_code_ttl_minutes=env.int("AUTH_CODE_TTL_MINUTES", 10),
        auth_code_max_attempts=env.int("AUTH_CODE_MAX_ATTEMPTS", 5),  # wrong guesses before the code is void
        auth_code_resend_seconds=env.int("AUTH_CODE_RESEND_SECONDS", 60),  # at most one code per this many seconds
        auth_session_hours=env.int("AUTH_SESSION_HOURS", 12),
        auth_cookie_name="session",
        # Send the cookie over HTTPS only. Keep false while the site is plain HTTP (it would never be sent back).
        auth_cookie_secure=env.bool("AUTH_COOKIE_SECURE", False),
        # Below this many reviewed machine values in the range there is not enough history to point at any pattern.
        insights_min_reviewed_fields=env.int("INSIGHTS_MIN_REVIEWED_FIELDS", 20),
        # A pattern is reported from this many events; from the next two counts its support is medium / high.
        insights_min_events=env.int("INSIGHTS_MIN_EVENTS", 3),
        insights_medium_support_events=env.int("INSIGHTS_MEDIUM_SUPPORT_EVENTS", 10),
        insights_high_support_events=env.int("INSIGHTS_HIGH_SUPPORT_EVENTS", 30),
        # A field is "often corrected" when at least this share (%) of its reviewed values were corrected.
        insights_min_correction_percent=env.int("INSIGHTS_MIN_CORRECTION_PERCENT", 20),
        # A pattern is "concentrated" in a form type / sender / way of writing when at least this share (%) is there.
        insights_concentration_percent=env.int("INSIGHTS_CONCENTRATION_PERCENT", 80),
        worker_enabled=env.bool("WORKER_ENABLED", True),
        # With LLM_ENABLED=false the queue still runs the free local stages (preprocessing, barcodes, OCR) — no tokens.
        llm_enabled=env.bool("LLM_ENABLED", True),
        # OCR-only values below this Tesseract confidence (0..100) are marked uncertain.
        local_ocr_min_confidence=env.int("LOCAL_OCR_MIN_CONFIDENCE", 60),
        worker_concurrency=env.int("WORKER_CONCURRENCY", 2),
        worker_idle_poll_seconds=env.int("WORKER_IDLE_POLL_SECONDS", 5),
        # Which providers read the page, in order. The first provider that answers is used; one that is out of quota,
        # overloaded or not configured hands the page to the next (integrations/llm/router.py).
        # Known providers: gemini, claude, openai.
        llm_providers=env.list("LLM_PROVIDERS") or ["gemini", "claude"],
        # Quota is per Google Cloud project: keys from different projects add up, keys of one project share it.
        gemini_api_keys=env.api_keys("GEMINI_API_KEY"),
        # Models to fall back to when the primary one is overloaded (503/504) or out of quota, in order. Each model
        # has its own daily quota. flash-lite is weaker (more extra/missed values — never "verified", go to review).
        gemini_models=list(dict.fromkeys([gemini_model, *(env.list("GEMINI_FALLBACK_MODELS") or ["models/gemini-3.5-flash-lite"])])),
        gemini_timeout_seconds=env.int("GEMINI_TIMEOUT_SECONDS", 120),
        gemini_max_attempts=env.int("GEMINI_MAX_ATTEMPTS", 2),
        # How long a key+model route rests after a failure before it is tried again:
        gemini_quota_default_backoff_seconds=env.int("GEMINI_QUOTA_DEFAULT_BACKOFF_SECONDS", 60),  # 429 without a retry time
        gemini_busy_cooldown_seconds=env.int("GEMINI_BUSY_COOLDOWN_SECONDS", 90),  # 500/503/504/timeout (model overloaded)
        gemini_invalid_key_cooldown_seconds=env.int("GEMINI_INVALID_KEY_COOLDOWN_SECONDS", 3600),  # 400/401/403 key rejected
        gemini_image_max_side_px=env.int("GEMINI_IMAGE_MAX_SIDE_PX", 1600),
        gemini_image_jpeg_quality=env.int("GEMINI_IMAGE_JPEG_QUALITY", 80),
        # ANTHROPIC_API_KEY, ANTHROPIC_API_KEY_2, ... — tried in turn. Rate limits are per Anthropic organization:
        # keys of one organization share them, so only keys from different organizations add capacity.
        anthropic_api_keys=env.api_keys("ANTHROPIC_API_KEY"),
        claude_model=env.str("CLAUDE_MODEL", "claude-opus-5-5"),
        # Thinking depth (low / medium / high / xhigh / max). Set explicitly: the model's own default is "medium".
        claude_effort=env.str("CLAUDE_EFFORT", "medium"),
        claude_max_tokens=env.int("CLAUDE_MAX_TOKENS", 16000),
        claude_timeout_seconds=env.int("CLAUDE_TIMEOUT_SECONDS", 180),
        # How long Claude rests after a failure before it is tried again (as for Gemini routes):
        claude_quota_default_backoff_seconds=env.int("CLAUDE_QUOTA_DEFAULT_BACKOFF_SECONDS", 60),  # 429 without retry-after
        claude_busy_cooldown_seconds=env.int("CLAUDE_BUSY_COOLDOWN_SECONDS", 90),  # overloaded / 5xx / timeout / network
        claude_invalid_key_cooldown_seconds=env.int("CLAUDE_INVALID_KEY_COOLDOWN_SECONDS", 3600),  # 401/403 key rejected
        # OpenAI: used for provider comparison (scripts/compare_providers.py); either spelling of the key.
        openai_api_key=(env.str("OPENAI_API_KEY") or env.str("OPEN_AI_API_KEY")).strip(),
        openai_model=env.str("OPENAI_MODEL", "gpt-5.4-mini"),  # same tier as Gemini Flash, for a fair comparison
        openai_api_url=env.str("OPENAI_API_URL", "https://api.openai.com/v1/chat/completions"),
        openai_timeout_seconds=env.int("OPENAI_TIMEOUT_SECONDS", 180),
        # MVP workaround for a local CA-certificate issue (Python 3.14 / Windows), used for Gemini, Claude and OpenAI
        # calls. Turn off in production.
        llm_insecure_ssl=env.bool("GEMINI_INSECURE_SSL", True),
        extraction_prompt_file=BASE_DIR / "prompts" / env.str("EXTRACTION_PROMPT_FILE", "extraction_prompt.md"),
    )
