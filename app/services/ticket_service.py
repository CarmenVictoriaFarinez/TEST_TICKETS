"""Application service for ticket creation, lookup, and sending.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from uuid import uuid4

from app.models.ticket import Ticket, TicketStatus
from app.providers.mock_provider import (
    ProviderTimeoutError,
    ProviderUnavailableError,
    TicketProvider,
)
from app.repositories.ticket_repository import TicketRepository
from app.schemas.ticket import TicketCreate

logger = logging.getLogger("abai.tickets")


class TicketNotFoundError(Exception):
    """Raised when a ticket id does not exist."""

    def __init__(self, ticket_id: str) -> None:
        self.ticket_id = ticket_id
        super().__init__(f"Ticket {ticket_id} not found")


class TicketService:
    def __init__(self, repository: TicketRepository, provider: TicketProvider) -> None:
        self.repository = repository
        self.provider = provider

    def create_ticket(self, data: TicketCreate) -> Ticket:
        ticket = Ticket(
            id=str(uuid4()),
            subject=data.subject,
            description=data.description,
            email=str(data.email),
            status=TicketStatus.PENDING,
            created_at=datetime.now(UTC),
            external_id=None,
        )
        self.repository.create(ticket)

        # Log only the identifier and outcome: never email or description.
        logger.info("ticket_created ticket_id=%s status=%s", ticket.id, ticket.status.value)
        return ticket

    def get_ticket(self, ticket_id: str) -> Ticket:
        ticket = self.repository.get(ticket_id)
        if ticket is None:
            raise TicketNotFoundError(ticket_id)
        return ticket

    def send_ticket(self, ticket_id: str) -> Ticket:
        ticket = self.get_ticket(ticket_id)

        if ticket.status is TicketStatus.SENT:
            logger.info(
                "ticket_send_skipped ticket_id=%s result=already_sent", ticket.id
            )
            return ticket

        try:
            external_id = self.provider.send(ticket.id)
        except ProviderTimeoutError:
            logger.warning("ticket_send_failed ticket_id=%s result=timeout", ticket.id)
            raise
        except ProviderUnavailableError:
            logger.warning(
                "ticket_send_failed ticket_id=%s result=unavailable", ticket.id
            )
            raise

        updated = self.repository.mark_sent(ticket.id, external_id)
        if updated is None:
            raise TicketNotFoundError(ticket.id)

        logger.info("ticket_sent ticket_id=%s result=sent", ticket.id)
        return updated
