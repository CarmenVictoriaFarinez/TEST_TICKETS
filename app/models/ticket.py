"""Domain model for a support ticket."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class TicketStatus(StrEnum):
    """The only two states allowed by the specification."""

    PENDING = "pending"
    SENT = "sent"


@dataclass(frozen=True, slots=True)
class Ticket:
    """Ticket as stored and returned by the application.

    Backend-owned fields (id, status, created_at, external_id) are part of the
    domain object but are never accepted from the create request schema.
    """

    id: str
    subject: str
    description: str
    email: str
    status: TicketStatus
    created_at: datetime
    external_id: str | None = None
