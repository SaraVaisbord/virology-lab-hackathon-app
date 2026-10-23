"""Composition root: builds the application's components from the configuration and wires them together.
Nothing else creates integrations or services — they receive what they need."""

from __future__ import annotations

from dataclasses import dataclass
from types import ModuleType

from db import queries
from domain.verification import VerificationRules
from integrations.imaging.barcode import scan_pil_image
from integrations.llm.base import LlmProvider
from integrations.llm.claude import ClaudeProvider, ClaudeSettings
from integrations.llm.gemini import GeminiProvider, GeminiSettings
from integrations.llm.openai import OpenAIProvider, OpenAISettings
from integrations.llm.page_image import PageImageSettings
from integrations.llm.prompt import ExtractionPrompt
from integrations.llm.router import LlmRouter
from integrations.ocr.base import OcrEngine
from integrations.ocr.local_extractor import LocalExtractor
from integrations.ocr.tesseract import TesseractEngine
from integrations.storage import Storage, build_storage
from services.extraction_pipeline import ExtractionPipeline
from services.extraction_queue import ExtractionQueue


def build_llm_providers(cfg: ModuleType) -> dict[str, LlmProvider]:
    prompt = ExtractionPrompt(cfg.EXTRACTION_PROMPT_FILE)
    image = PageImageSettings(max_side_px=cfg.GEMINI_IMAGE_MAX_SIDE_PX, jpeg_quality=cfg.GEMINI_IMAGE_JPEG_QUALITY)
    verify_tls = not cfg.GEMINI_INSECURE_SSL
    return {
        "gemini": GeminiProvider(GeminiSettings(
            api_keys=cfg.GEMINI_API_KEYS, models=cfg.GEMINI_MODELS, timeout_seconds=cfg.GEMINI_TIMEOUT_SECONDS,
            max_attempts=cfg.GEMINI_MAX_ATTEMPTS, quota_default_backoff_seconds=cfg.GEMINI_QUOTA_DEFAULT_BACKOFF_SECONDS,
            busy_cooldown_seconds=cfg.GEMINI_BUSY_COOLDOWN_SECONDS,
            invalid_key_cooldown_seconds=cfg.GEMINI_INVALID_KEY_COOLDOWN_SECONDS,
        ), prompt, image, verify_tls),
        "claude": ClaudeProvider(ClaudeSettings(
            api_keys=cfg.ANTHROPIC_API_KEYS, model=cfg.CLAUDE_MODEL, effort=cfg.CLAUDE_EFFORT, max_tokens=cfg.CLAUDE_MAX_TOKENS,
            timeout_seconds=cfg.CLAUDE_TIMEOUT_SECONDS, quota_default_backoff_seconds=cfg.CLAUDE_QUOTA_DEFAULT_BACKOFF_SECONDS,
            busy_cooldown_seconds=cfg.CLAUDE_BUSY_COOLDOWN_SECONDS,
            invalid_key_cooldown_seconds=cfg.CLAUDE_INVALID_KEY_COOLDOWN_SECONDS,
        ), prompt, image, verify_tls),
        "openai": OpenAIProvider(OpenAISettings(
            api_key=cfg.OPENAI_API_KEY, model=cfg.OPENAI_MODEL, api_url=cfg.OPENAI_API_URL,
            timeout_seconds=cfg.OPENAI_TIMEOUT_SECONDS,
        ), prompt, image, verify_tls),
    }


def verification_rules(cfg: ModuleType) -> VerificationRules:
    return VerificationRules(received_date_max_age_days=cfg.RECEIVED_DATE_MAX_AGE_DAYS,
                             local_ocr_min_confidence=cfg.LOCAL_OCR_MIN_CONFIDENCE)


def build_ocr(cfg: ModuleType) -> OcrEngine:
    return TesseractEngine(cfg.TESSERACT_CMD, cfg.OCR_TESSDATA_DIR, cfg.OCR_LANGUAGES, cfg.OCR_TIMEOUT_SECONDS)


def build_file_storage(cfg: ModuleType) -> Storage:
    return build_storage(cfg.STORAGE_BACKEND, cfg.DATA_DIR, cfg.S3_BUCKET, cfg.S3_PREFIX, cfg.AWS_REGION)


@dataclass
class Container:
    worker_enabled: bool
    storage: Storage
    ocr: OcrEngine
    llm: LlmRouter
    pipeline: ExtractionPipeline
    queue: ExtractionQueue


def build_container(cfg: ModuleType, *, llm_providers: dict[str, LlmProvider] | None = None, ocr: OcrEngine | None = None,
                    storage: Storage | None = None, scan_barcodes=scan_pil_image) -> Container:
    """Every component built from `cfg`; tests replace the outside world (LLM providers, OCR, storage, zbar)."""
    storage = storage or build_file_storage(cfg)
    ocr = ocr or build_ocr(cfg)
    llm = LlmRouter(llm_providers or build_llm_providers(cfg), cfg.LLM_PROVIDERS)
    pipeline = ExtractionPipeline(
        queries, storage, llm, LocalExtractor(ocr, cfg.RECEIVED_DATE_MAX_AGE_DAYS), scan_barcodes,
        verification_rules(cfg), page_render_dpi=cfg.PAGE_RENDER_DPI, llm_enabled=cfg.LLM_ENABLED,
    )
    queue = ExtractionQueue(pipeline, queries, cfg.WORKER_CONCURRENCY, cfg.WORKER_IDLE_POLL_SECONDS)
    return Container(worker_enabled=cfg.WORKER_ENABLED, storage=storage, ocr=ocr, llm=llm, pipeline=pipeline, queue=queue)
