from __future__ import annotations

from pathlib import Path

from domain.vocabulary import FORM_TYPES


class ExtractionPrompt:
    """The extraction prompt (a Markdown template file) filled with the known senders and form types.
    The file is read once, on first use."""

    def __init__(self, template_file: Path) -> None:
        self._template_file = template_file
        self._template: str | None = None

    def build(self, known_senders: list[str]) -> str:
        if self._template is None:
            self._template = self._template_file.read_text(encoding="utf-8")
        senders = "\n".join(f"- {name}" for name in known_senders) or "- (none)"
        form_types = " | ".join(f'"{form_type}"' for form_type in sorted(FORM_TYPES))
        return self._template.replace("{{known_senders}}", senders).replace("{{form_types}}", form_types)
