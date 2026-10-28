"""SQLite persistence for tickets."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from app.db import connect
from app.models.ticket import Ticket, TicketStatus


class TicketRepository:
    """Small repository around the single ``tickets`` table."""

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)

    def create(self, ticket: Ticket) -> None:
        with connect(self.db_path) as connection:
            with connection:
                connection.execute(
                    """
                    INSERT INTO tickets (
                        id, subject, description, email, status, created_at, external_id
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        ticket.id,
                        ticket.subject,
                        ticket.description,
                        ticket.email,
                        ticket.status.value,
                        ticket.created_at.isoformat(),
                        ticket.external_id,
                    ),
                )

    def get(self, ticket_id: str) -> Ticket | None:
        with connect(self.db_path) as connection:
            row = connection.execute(
                """
                SELECT id, subject, description, email, status, created_at, external_id
                FROM tickets
                WHERE id = ?
                """,
                (ticket_id,),
            ).fetchone()

        return self._row_to_ticket(row) if row is not None else None

    def mark_sent(self, ticket_id: str, external_id: str) -> Ticket | None:
        """Mark a pending ticket as sent and return its current state.

        The conditional ``WHERE status = 'pending'`` prevents a concurrent
        request from overwriting an external id already stored. It does not
        prevent two requests from calling the provider; that limitation is
        documented in the README.
        """

        with connect(self.db_path) as connection:
            with connection:
                connection.execute(
                    """
                    UPDATE tickets
                    SET status = ?, external_id = ?
                    WHERE id = ? AND status = ?
                    """,
                    (
                        TicketStatus.SENT.value,
                        external_id,
                        ticket_id,
                        TicketStatus.PENDING.value,
                    ),
                )

            row = connection.execute(
                """
                SELECT id, subject, description, email, status, created_at, external_id
                FROM tickets
                WHERE id = ?
                """,
                (ticket_id,),
            ).fetchone()

        return self._row_to_ticket(row) if row is not None else None

    @staticmethod
    def _row_to_ticket(row: sqlite3.Row) -> Ticket:
        created_at = datetime.fromisoformat(row["created_at"])
        if created_at.tzinfo is None:
            # Defensive fallback for manually inserted legacy rows.
            created_at = created_at.replace(tzinfo=UTC)

        return Ticket(
            id=row["id"],
            subject=row["subject"],
            description=row["description"],
            email=row["email"],
            status=TicketStatus(row["status"]),
            created_at=created_at,
            external_id=row["external_id"],
        )
