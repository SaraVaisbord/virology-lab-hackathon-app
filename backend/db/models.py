from __future__ import annotations

from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Float, ForeignKey, Integer, MetaData, String, Text, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from .constants import CONFIDENCE_LEVELS, FIELDS, FIELD_STATUSES, FORM_STATUSES, FORM_TYPES, SENDER_KINDS, SOURCE_LABELS


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


class Sender(Base):
    __tablename__ = "senders"
    __table_args__ = (CheckConstraint(f"kind IN {in_clause(SENDER_KINDS)}", name="kind"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
