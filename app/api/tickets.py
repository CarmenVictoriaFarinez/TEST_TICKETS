"""Ticket HTTP endpoints."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request

from app.models.ticket import Ticket
from app.schemas.ticket import TicketCreate, TicketOut
from app.services.ticket_service import TicketService

router = APIRouter(tags=["tickets"])


def get_ticket_service(request: Request) -> TicketService:
    return request.app.state.ticket_service


TicketServiceDep = Annotated[TicketService, Depends(get_ticket_service)]


@router.post(
    "/tickets",
    status_code=201,
    response_model=TicketOut,
    summary="Create a ticket",
)
def create_ticket(payload: TicketCreate, service: TicketServiceDep) -> Ticket:
    return service.create_ticket(payload)


@router.get(
    "/tickets/{ticket_id}",
    response_model=TicketOut,
    summary="Get a ticket by id",
)
def get_ticket(ticket_id: str, service: TicketServiceDep) -> Ticket:
    # The id is intentionally an opaque string. A malformed or unknown id is a
    # missing resource (404), not a schema-validation error (422).
    return service.get_ticket(ticket_id)


@router.post(
    "/tickets/{ticket_id}/send",
    response_model=TicketOut,
    summary="Send a ticket to the mock provider",
)
def send_ticket(ticket_id: str, service: TicketServiceDep) -> Ticket:
    return service.send_ticket(ticket_id)
