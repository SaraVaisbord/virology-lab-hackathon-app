"""The three ways an LLM provider can fail — shared by every provider, the router and the extraction queue."""

from __future__ import annotations


class ExtractionError(RuntimeError):
    """Raised when the model call fails or returns something unusable."""


class MissingApiKeyError(ExtractionError):
    """The provider is not configured (no API key), or every key was rejected."""


class ModelsUnavailableError(ExtractionError):
    """Every key+model route is resting (quota or overload). Not the form's fault — the queue pauses and retries.

    reason: "quota" when every route hit its quota, "busy" otherwise.
    """

    def __init__(self, message: str, retry_after_seconds: float, reason: str):
        super().__init__(message)
        self.retry_after_seconds = retry_after_seconds
        self.reason = reason
