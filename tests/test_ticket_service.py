from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from app.db import init_db
from app.models.ticket import TicketStatus
from app.providers.mock_provider import MockProvider
from app.repositories.ticket_repository import TicketRepository
from app.schemas.ticket import TicketCreate
from app.services.ticket_service import TicketNotFoundError, TicketService


@pytest.fixture
def service(db_path: Path) -> TicketService:
    init_db(db_path)
    return TicketService(TicketRepository(db_path), MockProvider())


def test_create_ticket_sets_backend_owned_values(service: TicketService) -> None:
    ticket = service.create_ticket(
        TicketCreate(
            subject="Asunto",
            description="Descripción",
            email="user@example.com",
        )
    )

    assert ticket.status is TicketStatus.PENDING
    assert ticket.external_id is None
    assert ticket.created_at.tzinfo is not None
    assert ticket.created_at.utcoffset() == datetime.now(UTC).utcoffset()
    assert service.get_ticket(ticket.id) == ticket


def test_get_missing_ticket_raises(service: TicketService) -> None:
    with pytest.raises(TicketNotFoundError):
        service.get_ticket("missing-ticket")


def test_unexpected_provider_errors_are_not_converted(db_path: Path) -> None:
    class BrokenProvider:
        def send(self, ticket_id: str) -> str:
            raise RuntimeError("unexpected provider error")

    init_db(db_path)
    service = TicketService(TicketRepository(db_path), BrokenProvider())
    ticket = service.create_ticket(
        TicketCreate(
            subject="Asunto",
            description="Descripción",
            email="user@example.com",
        )
    )

    with pytest.raises(RuntimeError):
        service.send_ticket(ticket.id)

    assert service.get_ticket(ticket.id).status is TicketStatus.PENDING
