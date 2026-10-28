"""Pydantic schemas for request validation and HTTP responses."""

from __future__ import annotations

from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_serializer, field_validator

from app.models.ticket import TicketStatus


class TicketCreate(BaseModel):
    """Input accepted by ``POST /tickets``.

    ``extra="forbid"`` is deliberate: backend-owned fields such as ``id``,
    ``status``, ``created_at`` and ``external_id`` must be rejected rather than
    silently ignored. The request contract therefore has exactly three fields.

    Whitespace is removed *before* the length checks (``mode="before"``
    validators run before field constraints), so a value made only of spaces is
    invalid and the persisted value is the trimmed one.
    """

    model_config = ConfigDict(extra="forbid")

    subject: str = Field(min_length=1, max_length=120)
    description: str = Field(min_length=1, max_length=2000)
    email: EmailStr

    @field_validator("subject", "description", mode="before")
    @classmethod
    def strip_text(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip()
        return value

    @field_validator("email", mode="before")
    @classmethod
    def strip_email(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip()
        return value


class TicketOut(BaseModel):
    """Public representation of a ticket.

    The explicit serializer guarantees a stable ISO-8601 UTC representation
    with a ``Z`` suffix, independent of the database representation.
    """

    model_config = ConfigDict(from_attributes=True)

    id: str
    subject: str
    description: str
    email: str
    status: TicketStatus
    created_at: datetime
    external_id: str | None

    @field_serializer("created_at")
    def serialize_created_at(self, value: datetime) -> str:
        return value.astimezone(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")
