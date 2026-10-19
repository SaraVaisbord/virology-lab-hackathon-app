"""Background extraction queue.

The queue itself is the `forms` table (status 'uploaded'); worker threads atomically claim forms one by one,
so the queue survives restarts and several workers never process the same form.
When Gemini reports a quota/rate limit, the form goes back to the queue and all workers pause until the
time Google asked us to wait.
"""

from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timezone

import config
from ai_extractor import QuotaExceededError
from db import queries
from services.extraction_service import extract_for_form, user_facing_error

logger = logging.getLogger(__name__)


class ExtractionQueue:
    def __init__(self, concurrency: int, idle_poll_seconds: float) -> None:
        self._concurrency = max(1, concurrency)
        self._idle_poll_seconds = idle_poll_seconds
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._threads: list[threading.Thread] = []
        self._lock = threading.Lock()
        self._paused_until = 0.0  # epoch seconds
        self._pause_reason: str | None = None

    def start(self) -> None:
        if self._threads:
            return
        requeued = queries.requeue_stale_processing()
        if requeued:
            logger.info("Re-queued %d forms left in 'processing'", requeued)
        self._stop.clear()
        self._threads = [
            threading.Thread(target=self._run, name=f"extraction-worker-{index}", daemon=True)
            for index in range(self._concurrency)
        ]
        for thread in self._threads:
            thread.start()

    def stop(self, timeout: float = 5.0) -> None:
        self._stop.set()
        self._wake.set()
        for thread in self._threads:
            thread.join(timeout=timeout)
        self._threads = []

    def notify(self) -> None:
        """Call after new forms are queued, so idle workers start immediately."""
        self._wake.set()

    def state(self) -> dict:
        with self._lock:
            running = bool(self._threads)
            paused = running and self._paused_until > time.time()
            return {
                "running": running,
                "paused_until": datetime.fromtimestamp(self._paused_until, timezone.utc) if paused else None,
                # Workers not started at all (WORKER_ENABLED=false) is reported as its own reason.
                "pause_reason": self._pause_reason if paused else None if running else "disabled",
            }

    def pause(self, seconds: float, reason: str) -> None:
        with self._lock:
            self._paused_until = max(self._paused_until, time.time() + seconds)
            self._pause_reason = reason

    def _seconds_until_resume(self) -> float:
        with self._lock:
            return max(0.0, self._paused_until - time.time())

    def _run(self) -> None:
        while not self._stop.is_set():
            wait = self._seconds_until_resume()
            if wait:
                self._stop.wait(min(wait, self._idle_poll_seconds))
                continue
            form = queries.claim_next_form()
            if form is None:
                self._wake.wait(self._idle_poll_seconds)
                self._wake.clear()
                continue
            self.process(form)

    def process(self, form: dict) -> None:
        try:
            extract_for_form(form)
            logger.info("Form %s extracted", form["id"])
        except QuotaExceededError as exc:
            logger.warning("Gemini quota exceeded — pausing queue for %.0fs", exc.retry_after_seconds)
            queries.return_to_queue(form["id"])
            self.pause(exc.retry_after_seconds, "quota")
        except Exception as exc:
            logger.exception("Extraction failed for form %s", form["id"])
            queries.set_form_status(form["id"], "failed", error=user_facing_error(exc))


extraction_queue = ExtractionQueue(config.WORKER_CONCURRENCY, config.WORKER_IDLE_POLL_SECONDS)
