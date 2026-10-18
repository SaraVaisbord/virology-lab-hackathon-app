from __future__ import annotations

from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, MetaData, String, Text, func
from sqlalchemy.orm import Mapped, DeclarativeBase, mapped_column, relationship

from .constants import FIELDS, FIELD_STATUSES, FORM_STATUSES, FORM_TYPES, SENDER_KINDS


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


def _in_clause(values: set[str]) -> str:
    return "(" + ", ".join(f"'{value}'" for value in sorted(values)) + ")"


class Form(Base):
    __tablename__ = "forms"
    __table_args__ = (
        CheckConstraint(f"status IN {_in_clause(FORM_STATUSES)}", name="status"),
        CheckConstraint(
            f"(form_type IN {_in_clause(FORM_TYPES)} OR form_type IS NULL)",
            name="form_type",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_file: Mapped[str] = mapped_column(String(255), nullable=False)
    file_hash: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    page_number: Mapped[int] = mapped_column(Integer, nullable=False)
    image_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    form_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="uploaded", index=True)
    raw_llm_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=func.now(),
        default=datetime.utcnow,
    )

    extracted_fields: Mapped[list["ExtractedField"]] = relationship(
        back_populates="form",
        cascade="all, delete-orphan",
    )


class ExtractedField(Base):
    __tablename__ = "extracted_fields"
    __table_args__ = (
        CheckConstraint(f"field_name IN {_in_clause(FIELDS)}", name="field_name"),
        CheckConstraint(f"status IN {_in_clause(FIELD_STATUSES)}", name="status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    form_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("forms.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    field_name: Mapped[str] = mapped_column(String(64), nullable=False)
    value: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    ocr_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    llm_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="unverified")
    corrected_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    bbox: Mapped[str | None] = mapped_column(Text, nullable=True)
    page: Mapped[int | None] = mapped_column(Integer, nullable=True)
    x: Mapped[float | None] = mapped_column(String(64), nullable=True)
    y: Mapped[float | None] = mapped_column(String(64), nullable=True)
    width: Mapped[float | None] = mapped_column(String(64), nullable=True)
    height: Mapped[float | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=func.now(),
        default=datetime.utcnow,
    )

    form: Mapped[Form] = relationship(back_populates="extracted_fields")


class Sender(Base):
    __tablename__ = "senders"
    __table_args__ = (
        CheckConstraint(f"kind IN {_in_clause(SENDER_KINDS)}", name="kind"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=func.now(),
        default=datetime.utcnow,
    )
