"""Composition root: builds the application's components from the settings and wires them together.
Nothing else creates integrations, repositories or services — they receive what they need."""

from __future__ import annotations

from dataclasses import dataclass

from config import Settings
from db.repositories import CorrectionHistory, FormListing, FormRepository, ReviewRepository, SenderRepository
from db.session import Database
from domain.verification import VerificationRules
from integrations.imaging.barcode import scan_pil_image
from integrations.llm.base import LlmProvider
from integrations.llm.claude import ClaudeProvider, ClaudeSettings
from integrations.llm.gemini import GeminiProvider, GeminiSettings
from integrations.llm.openai import OpenAIProvider, OpenAISettings
from integrations.llm.page_image import PageImageSettings
from integrations.llm.prompt import ExtractionPrompt
from integrations.llm.router import LlmRouter
from integrations.llm.tls import TlsSettings
from integrations.mailer import Mailer, SmtpMailer, SmtpSettings
from integrations.ocr.base import OcrEngine
from integrations.ocr.local_extractor import LocalExtractor
from integrations.ocr.tesseract import TesseractEngine
from integrations.storage import Storage, build_storage
from services.auth_service import AuthService, AuthSettings
from services.export_service import ExportService
from services.extraction_pipeline import BarcodeScanner, ExtractionPipeline
from services.extraction_queue import ExtractionQueue
from services.insights_service import InsightsService, InsightThresholds
from services.review_service import ReviewService
from services.upload_service import UploadService, UploadSettings


def build_llm_providers(settings: Settings) -> dict[str, LlmProvider]:
    prompt = ExtractionPrompt(settings.extraction_prompt_file)
    image = PageImageSettings(max_side_px=settings.gemini_image_max_side_px, jpeg_quality=settings.gemini_image_jpeg_quality)
    tls = TlsSettings(ca_bundle=settings.llm_ca_bundle, insecure=settings.llm_insecure_ssl)
    return {
        "gemini": GeminiProvider(GeminiSettings(
            api_keys=settings.gemini_api_keys, models=settings.gemini_models, timeout_seconds=settings.gemini_timeout_seconds,
            max_attempts=settings.gemini_max_attempts,
            quota_default_backoff_seconds=settings.gemini_quota_default_backoff_seconds,
            busy_cooldown_seconds=settings.gemini_busy_cooldown_seconds,
            invalid_key_cooldown_seconds=settings.gemini_invalid_key_cooldown_seconds,
        ), prompt, image, tls),
        "claude": ClaudeProvider(ClaudeSettings(
            api_keys=settings.anthropic_api_keys, model=settings.claude_model, effort=settings.claude_effort,
            max_tokens=settings.claude_max_tokens, timeout_seconds=settings.claude_timeout_seconds,
            quota_default_backoff_seconds=settings.claude_quota_default_backoff_seconds,
            busy_cooldown_seconds=settings.claude_busy_cooldown_seconds,
            invalid_key_cooldown_seconds=settings.claude_invalid_key_cooldown_seconds,
        ), prompt, image, tls),
        "openai": OpenAIProvider(OpenAISettings(
            api_key=settings.openai_api_key, model=settings.openai_model, api_url=settings.openai_api_url,
            timeout_seconds=settings.openai_timeout_seconds,
        ), prompt, image, tls),
    }


def verification_rules(settings: Settings) -> VerificationRules:
    return VerificationRules(received_date_max_age_days=settings.received_date_max_age_days,
                             local_ocr_min_confidence=settings.local_ocr_min_confidence)


def build_ocr(settings: Settings) -> OcrEngine:
    return TesseractEngine(settings.tesseract_cmd, settings.ocr_tessdata_dir, settings.ocr_languages, settings.ocr_timeout_seconds)


def build_file_storage(settings: Settings) -> Storage:
    return build_storage(settings.storage_backend, settings.data_dir, settings.s3_bucket, settings.s3_prefix, settings.aws_region)


def build_mailer(settings: Settings) -> SmtpMailer:
    return SmtpMailer(SmtpSettings(host=settings.smtp_host, port=settings.smtp_port, username=settings.smtp_username,
                                   password=settings.smtp_password, sender=settings.smtp_from,
                                   timeout_seconds=settings.smtp_timeout_seconds))


def auth_settings(settings: Settings, mail_configured: bool) -> AuthSettings:
    return AuthSettings(
        enabled=settings.auth_enabled, email=settings.auth_email, mail_configured=mail_configured,
        demo_code=settings.auth_demo_code, secret=settings.auth_secret, code_ttl_minutes=settings.auth_code_ttl_minutes,
        code_max_attempts=settings.auth_code_max_attempts, code_resend_seconds=settings.auth_code_resend_seconds,
        session_hours=settings.auth_session_hours,
    )


def insight_thresholds(settings: Settings) -> InsightThresholds:
    return InsightThresholds(
        min_reviewed_fields=settings.insights_min_reviewed_fields, min_events=settings.insights_min_events,
        medium_support_events=settings.insights_medium_support_events, high_support_events=settings.insights_high_support_events,
        min_correction_percent=settings.insights_min_correction_percent, concentration_percent=settings.insights_concentration_percent,
    )


@dataclass
class Container:
    settings: Settings
    database: Database
    forms: FormRepository
    review: ReviewRepository
    listing: FormListing
    history: CorrectionHistory
    senders: SenderRepository
    storage: Storage
    ocr: OcrEngine
    llm: LlmRouter
    pipeline: ExtractionPipeline
    queue: ExtractionQueue
    uploads: UploadService
    reviews: ReviewService
    exports: ExportService
    insights: InsightsService
    auth: AuthService

    def close(self) -> None:
        self.queue.stop()
        self.database.dispose()


def build_container(settings: Settings, *, llm_providers: dict[str, LlmProvider] | None = None, ocr: OcrEngine | None = None,
                    storage: Storage | None = None, mailer: Mailer | None = None,
                    scan_barcodes: BarcodeScanner = scan_pil_image) -> Container:
    """Every component built from `settings`; tests replace the outside world (LLM providers, OCR, storage, mail, zbar)."""
    database = Database(settings.database_url)
    sessions = database.sessions
    forms, review, senders = FormRepository(sessions), ReviewRepository(sessions), SenderRepository(sessions)
    listing, history = FormListing(sessions), CorrectionHistory(sessions)
    storage = storage if storage is not None else build_file_storage(settings)
    ocr = ocr if ocr is not None else build_ocr(settings)
    llm = LlmRouter(llm_providers if llm_providers is not None else build_llm_providers(settings), settings.llm_providers)
    pipeline = ExtractionPipeline(
        forms, senders, storage, llm, LocalExtractor(ocr, settings.received_date_max_age_days), scan_barcodes,
        verification_rules(settings), page_render_dpi=settings.page_render_dpi, llm_enabled=settings.llm_enabled,
    )
    queue = ExtractionQueue(pipeline, forms, settings.worker_concurrency, settings.worker_idle_poll_seconds)
    smtp = build_mailer(settings)
    upload_settings = UploadSettings(max_file_size_mb=settings.max_file_size_mb, page_render_dpi=settings.page_render_dpi,
                                     page_max_side_px=settings.page_max_side_px, page_workers=settings.upload_page_workers)
    return Container(
        settings=settings, database=database, forms=forms, review=review, listing=listing, history=history, senders=senders,
        storage=storage, ocr=ocr, llm=llm, pipeline=pipeline, queue=queue,
        uploads=UploadService(forms, storage, ocr, upload_settings),
        reviews=ReviewService(forms, review, storage, queue),
        exports=ExportService(listing, settings.export_max_rows),
        insights=InsightsService(history, senders, insight_thresholds(settings)),
        auth=AuthService(auth_settings(settings, smtp.settings.configured), mailer if mailer is not None else smtp),
    )
