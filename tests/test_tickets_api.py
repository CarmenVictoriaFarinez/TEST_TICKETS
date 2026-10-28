from __future__ import annotations

import logging
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from app.main import create_app

BASE_PAYLOAD = {
    "subject": "No puedo acceder",
    "description": "La aplicación devuelve un error.",
    "email": "user@example.com",
}

EXPECTED_KEYS = {
    "id",
    "subject",
    "description",
    "email",
    "status",
    "created_at",
    "external_id",
}


def row_count(db_path: Path) -> int:
    with sqlite3.connect(str(db_path)) as connection:
        return connection.execute("SELECT COUNT(*) FROM tickets").fetchone()[0]


def fetch_row(db_path: Path, ticket_id: str) -> sqlite3.Row | None:
    with sqlite3.connect(str(db_path)) as connection:
        connection.row_factory = sqlite3.Row
        return connection.execute(
            "SELECT * FROM tickets WHERE id = ?", (ticket_id,)
        ).fetchone()


def test_create_ticket_returns_201_with_backend_fields(
    client: TestClient, db_path: Path
) -> None:
    response = client.post("/tickets", json=BASE_PAYLOAD)

    assert response.status_code == 201
    body = response.json()
    assert set(body) == EXPECTED_KEYS
    assert body["subject"] == BASE_PAYLOAD["subject"]
    assert body["description"] == BASE_PAYLOAD["description"]
    assert body["email"] == BASE_PAYLOAD["email"]
    assert body["status"] == "pending"
    assert body["external_id"] is None

    ticket_id = UUID(body["id"])
    assert ticket_id.version == 4

    created_at = body["created_at"]
    assert created_at.endswith("Z")
    parsed_created_at = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
    assert parsed_created_at.tzinfo is not None
    assert parsed_created_at.utcoffset() == timedelta(0)
    assert abs(datetime.now(UTC) - parsed_created_at) < timedelta(seconds=60)

    assert row_count(db_path) == 1
    row = fetch_row(db_path, body["id"])
    assert row is not None
    assert row["subject"] == BASE_PAYLOAD["subject"]
    assert row["description"] == BASE_PAYLOAD["description"]
    assert row["email"] == BASE_PAYLOAD["email"]
    assert row["status"] == "pending"
    assert row["external_id"] is None


def test_get_ticket_returns_the_persisted_ticket(client: TestClient) -> None:
    created = client.post("/tickets", json=BASE_PAYLOAD)
    assert created.status_code == 201

    response = client.get(f"/tickets/{created.json()['id']}")

    assert response.status_code == 200
    assert response.json() == created.json()


def test_trim_is_applied_before_validation_and_persistence(
    client: TestClient,
) -> None:
    response = client.post(
        "/tickets",
        json={
            "subject": "  Hola  ",
            "description": "  línea 1\nlínea 2  ",
            "email": "  user@example.com  ",
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["subject"] == "Hola"
    assert body["description"] == "línea 1\nlínea 2"
    assert body["email"] == "user@example.com"

    persisted = client.get(f"/tickets/{body['id']}")
    assert persisted.status_code == 200
    assert persisted.json() == body


def test_maximum_lengths_are_accepted_after_trim(client: TestClient) -> None:
    response = client.post(
        "/tickets",
        json={
            "subject": "  " + "a" * 120 + "  ",
            "description": "  " + "b" * 2000 + "  ",
            "email": "user@example.com",
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert len(body["subject"]) == 120
    assert len(body["description"]) == 2000


@pytest.mark.parametrize(
    "payload",
    [
        {**BASE_PAYLOAD, "subject": ""},
        {**BASE_PAYLOAD, "subject": "   "},
        {**BASE_PAYLOAD, "subject": "a" * 121},
        {**BASE_PAYLOAD, "subject": None},
        {**BASE_PAYLOAD, "subject": 123},
        {**BASE_PAYLOAD, "description": ""},
        {**BASE_PAYLOAD, "description": "   "},
        {**BASE_PAYLOAD, "description": "b" * 2001},
        {**BASE_PAYLOAD, "description": None},
        {**BASE_PAYLOAD, "description": 123},
        {**BASE_PAYLOAD, "email": "not-an-email"},
        {**BASE_PAYLOAD, "email": "a@b"},
        {**BASE_PAYLOAD, "email": "user@"},
        {**BASE_PAYLOAD, "email": ""},
        {**BASE_PAYLOAD, "email": None},
        {**BASE_PAYLOAD, "email": 123},
        {key: value for key, value in BASE_PAYLOAD.items() if key != "subject"},
        {key: value for key, value in BASE_PAYLOAD.items() if key != "description"},
        {key: value for key, value in BASE_PAYLOAD.items() if key != "email"},
        {**BASE_PAYLOAD, "id": str(uuid4())},
        {**BASE_PAYLOAD, "status": "sent"},
        {**BASE_PAYLOAD, "created_at": "2026-01-01T00:00:00Z"},
        {**BASE_PAYLOAD, "external_id": "ext-123"},
        {**BASE_PAYLOAD, "unexpected": "field"},
    ],
)
def test_invalid_create_is_rejected_and_not_persisted(
    client: TestClient, db_path: Path, payload: dict[str, object]
) -> None:
    response = client.post("/tickets", json=payload)

    assert response.status_code == 422
    assert row_count(db_path) == 0


@pytest.mark.parametrize("ticket_id", ["does-not-exist", str(uuid4())])
def test_get_unknown_ticket_returns_404(
    client: TestClient, ticket_id: str
) -> None:
    response = client.get(f"/tickets/{ticket_id}")

    assert response.status_code == 404
    assert response.json()["detail"] == "Ticket not found"


def test_create_log_contains_id_and_status_but_no_pii(
    client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO, logger="abai.tickets")
    email = "private@example.com"
    description = "private-description-value"

    response = client.post(
        "/tickets",
        json={
            "subject": "private-subject-value",
            "description": description,
            "email": email,
        },
    )

    assert response.status_code == 201
    ticket_id = response.json()["id"]
    assert "ticket_created" in caplog.text
    assert ticket_id in caplog.text
    assert "status=pending" in caplog.text
    assert email not in caplog.text
    assert description not in caplog.text


def test_tickets_survive_an_app_restart(db_path: Path) -> None:
    first_app = create_app(db_path=db_path)
    with TestClient(first_app) as first_client:
        created = first_client.post("/tickets", json=BASE_PAYLOAD)
        assert created.status_code == 201
        expected = created.json()

    second_app = create_app(db_path=db_path)
    with TestClient(second_app) as second_client:
        response = second_client.get(f"/tickets/{expected['id']}")

    assert response.status_code == 200
    assert response.json() == expected
