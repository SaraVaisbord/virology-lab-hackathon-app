from __future__ import annotations

from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Float, ForeignKey, Integer, MetaData, String, Text, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from domain.vocabulary import (
    CHANGE_KINDS,
    CONFIDENCE_LEVELS,
    FIELD_EVENT_ACTIONS,
    FIELDS,
    FIELD_STATUSES,
    FORM_STATUSES,
    FORM_TYPES,
    INVENTORY_KINDS,
    SENDER_KINDS,
    SOURCE_LABELS,
    VALUE_ORIGINS,
)


class Base(DeclarativeBase):
    metadata = MetaData(
        naming_convention={
            "ix": "ix_%(column_0_label)s",
            "uq": "uq_%(table_name)s_%(column_0_name)s",
            "ck": "ck_%(table_name)s_%(constraint_name)s",
            "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
            "pk": "pk_%(table_name)s",
        }
    )


def in_clause(values) -> str:
    return "(" + ", ".join(f"'{value}'" for value in sorted(values)) + ")"


class Form(Base):
    """One page of an uploaded document."""

    __tablename__ = "forms"
    __table_args__ = (
        CheckConstraint(f"status IN {in_clause(FORM_STATUSES)}", name="status"),
        CheckConstraint(f"(form_type IN {in_clause(FORM_TYPES)} OR form_type IS NULL)", name="form_type"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_file: Mapped[str] = mapped_column(String(255), nullable=False)
    file_hash: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    page_number: Mapped[int] = mapped_column(Integer, nullable=False)
    image_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    form_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="uploaded", index=True)
    # Raw evidence from each source, stored separately and never overwritten by another source (JSON text):
    llm_result: Mapped[str | None] = mapped_column(Text, nullable=True)  # Gemini's response as returned
    barcode_result: Mapped[str | None] = mapped_column(Text, nullable=True)  # {"status", "items" | "error"}
    ocr_result: Mapped[str | None] = mapped_column(Text, nullable=True)  # {"status", "items" | "reason"}
    source_errors: Mapped[str | None] = mapped_column(Text, nullable=True)  # {"llm": "...", ...} per failed source
    # Values the lab worker deleted ({"field_name": [value, ...]}, JSON): re-extraction never puts them back.
    rejected_values: Mapped[str | None] = mapped_column(Text, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())

    extracted_fields: Mapped[list["ExtractedField"]] = relationship(
        back_populates="form",
        cascade="all, delete-orphan",
        order_by="ExtractedField.id",
    )


class ExtractedField(Base):
    """One extracted value. Multi-value fields (see MULTI_VALUE_FIELDS) have one row per value.

    `llm_value` / `barcode_value` / `ocr_value` keep what each source read, unmodified; `value` is the
    normalized value shown to the user. `evidence` (JSON) holds all per-source candidates, the assignment
    evidence and the agreement verdict. Coordinates are normalized to the page image (0..1);
    `box_source` says which source they came from.
    """

    __tablename__ = "extracted_fields"
    __table_args__ = (
        CheckConstraint(f"field_name IN {in_clause(FIELDS)}", name="field_name"),
        CheckConstraint(f"status IN {in_clause(FIELD_STATUSES)}", name="status"),
        CheckConstraint(f"(confidence IN {in_clause(CONFIDENCE_LEVELS)} OR confidence IS NULL)", name="confidence"),
        CheckConstraint(f"(box_source IN {in_clause(SOURCE_LABELS)} OR box_source IS NULL)", name="box_source"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    form_id: Mapped[int] = mapped_column(Integer, ForeignKey("forms.id", ondelete="CASCADE"), nullable=False, index=True)
    field_name: Mapped[str] = mapped_column(String(64), nullable=False)
    value: Mapped[str | None] = mapped_column(Text, nullable=True)
    llm_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    barcode_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    ocr_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    corrected_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence: Mapped[str | None] = mapped_column(Text, nullable=True)
    box_source: Mapped[str | None] = mapped_column(String(16), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="unverified")
    confidence: Mapped[str | None] = mapped_column(String(16), nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    page: Mapped[int | None] = mapped_column(Integer, nullable=True)
    x: Mapped[float | None] = mapped_column(Float, nullable=True)
    y: Mapped[float | None] = mapped_column(Float, nullable=True)
    width: Mapped[float | None] = mapped_column(Float, nullable=True)
    height: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())

    form: Mapped[Form] = relationship(back_populates="extracted_fields")


class FieldEvent(Base):
    """One action of the lab worker on a field — appended, never updated: the correction history.

    Holds no field values (they may identify the patient): only what kind of change it was and the field's state
    just before it. The values stay in extracted_fields, reached through form_id / field_id. field_id is the field
    as it is after the action (the new row when a value was replaced), and NULL once that row is deleted —
    `previous_event_id` keeps the history of one value connected across those rows.
    Source lists (`before_sources`, `correct_seen_by`) are comma-separated SOURCE_LABELS keys.
    """

    __tablename__ = "field_events"
    __table_args__ = (
        CheckConstraint(f"field_name IN {in_clause(FIELDS)}", name="field_name"),
        CheckConstraint(f"action IN {in_clause(FIELD_EVENT_ACTIONS)}", name="action"),
        CheckConstraint(f"change_kind IN {in_clause(CHANGE_KINDS)}", name="change_kind"),
        CheckConstraint(f"(matched_field IN {in_clause(FIELDS)} OR matched_field IS NULL)", name="matched_field"),
        CheckConstraint(f"before_origin IN {in_clause(VALUE_ORIGINS)}", name="before_origin"),
        CheckConstraint(f"(before_status IN {in_clause(FIELD_STATUSES)} OR before_status IS NULL)", name="before_status"),
        CheckConstraint(f"(before_confidence IN {in_clause(CONFIDENCE_LEVELS)} OR before_confidence IS NULL)", name="before_confidence"),
        CheckConstraint(f"(before_written_as IN {in_clause(INVENTORY_KINDS)} OR before_written_as IS NULL)", name="before_written_as"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    form_id: Mapped[int] = mapped_column(Integer, ForeignKey("forms.id", ondelete="CASCADE"), nullable=False, index=True)
    field_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("extracted_fields.id", ondelete="SET NULL"), nullable=True, index=True
    )
    # The previous event of the same value (same row, the row it replaced, or the deletion it refills).
    previous_event_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("field_events.id", ondelete="SET NULL"), nullable=True
    )
    field_name: Mapped[str] = mapped_column(String(64), nullable=False)
    action: Mapped[str] = mapped_column(String(16), nullable=False)
    change_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    chars_changed: Mapped[int | None] = mapped_column(Integer, nullable=True)  # set for a typo only
    matched_field: Mapped[str | None] = mapped_column(String(64), nullable=True)  # wrong_field / removed: where it was
    digit_swaps: Mapped[str | None] = mapped_column(String(32), nullable=True)  # typo: "1>7,0>8" — no value, only the swap
    before_origin: Mapped[str] = mapped_column(String(32), nullable=False)
    before_written_as: Mapped[str | None] = mapped_column(String(16), nullable=True)  # INVENTORY_KINDS, as the AI saw it
    before_status: Mapped[str | None] = mapped_column(String(32), nullable=True)  # NULL: the field had no row
    before_confidence: Mapped[str | None] = mapped_column(String(16), nullable=True)
    before_sources: Mapped[str | None] = mapped_column(String(64), nullable=True)  # sources behind the shown value
    correct_seen_by: Mapped[str | None] = mapped_column(String(64), nullable=True)  # sources that read the new value
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())


class Sender(Base):
    __tablename__ = "senders"
    __table_args__ = (CheckConstraint(f"kind IN {in_clause(SENDER_KINDS)}", name="kind"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
