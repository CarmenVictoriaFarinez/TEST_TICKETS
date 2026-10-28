from __future__ import annotations

import logging
import sqlite3
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.main import create_app
from app.providers.mock_provider import MockProvider, ProviderMode

BASE_PAYLOAD = {
    "subject": "No puedo acceder",
    "description": "La aplicación devuelve un error.",
    "email": "user@example.com",
}


def create_ticket(client: TestClient) -> dict[str, object]:
    response = client.post("/tickets", json=BASE_PAYLOAD)
    assert response.status_code == 201
    return response.json()


def fetch_row(db_path: Path, ticket_id: str) -> sqlite3.Row | None:
    with sqlite3.connect(str(db_path)) as connection:
        connection.row_factory = sqlite3.Row
        return connection.execute(
            "SELECT * FROM tickets WHERE id = ?", (ticket_id,)
        ).fetchone()


def test_send_success_marks_ticket_as_sent(
    client: TestClient, provider, db_path: Path
) -> None:
    ticket = create_ticket(client)

    response = client.post(f"/tickets/{ticket['id']}/send")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "sent"
    assert body["external_id"] == f"ext_{ticket['id']}"
    assert provider.calls == [ticket["id"]]

    persisted = client.get(f"/tickets/{ticket['id']}")
    assert persisted.status_code == 200
    assert persisted.json() == body

    row = fetch_row(db_path, str(ticket["id"]))
    assert row is not None
    assert row["status"] == "sent"
    assert row["external_id"] == body["external_id"]


def test_send_unknown_ticket_returns_404_without_calling_provider(
    client: TestClient, provider
) -> None:
    response = client.post("/tickets/does-not-exist/send")

    assert response.status_code == 404
    assert response.json()["detail"] == "Ticket not found"
    assert provider.calls == []


@pytest.mark.parametrize(
    ("mode", "expected_status"),
    [
        ("timeout", 504),
        ("error", 502),
    ],
)
def test_app_reads_provider_mode_from_environment(
    monkeypatch: pytest.MonkeyPatch,
    db_path: Path,
    mode: str,
    expected_status: int,
) -> None:
    monkeypatch.setenv("PROVIDER_MODE", mode)
    app = create_app(db_path=db_path)

    with TestClient(app) as env_client:
        ticket = create_ticket(env_client)
        response = env_client.post(f"/tickets/{ticket['id']}/send")

    assert response.status_code == expected_status


def test_send_timeout_returns_504_and_keeps_ticket_pending(
    client: TestClient, provider, db_path: Path
) -> None:
    ticket = create_ticket(client)
    provider.mode = ProviderMode.TIMEOUT

    response = client.post(f"/tickets/{ticket['id']}/send")

    assert response.status_code == 504
    assert response.json()["detail"] == "Provider timed out"
    assert provider.calls == [ticket["id"]]

    current = client.get(f"/tickets/{ticket['id']}").json()
    assert current == ticket
    assert current["status"] == "pending"
    assert current["external_id"] is None

    row = fetch_row(db_path, str(ticket["id"]))
    assert row is not None
    assert row["status"] == "pending"
    assert row["external_id"] is None


def test_send_unavailable_returns_502_and_keeps_ticket_pending(
    client: TestClient, provider, db_path: Path
) -> None:
    ticket = create_ticket(client)
    provider.mode = ProviderMode.ERROR

    response = client.post(f"/tickets/{ticket['id']}/send")

    assert response.status_code == 502
    assert response.json()["detail"] == "Provider unavailable"
    assert provider.calls == [ticket["id"]]

    current = client.get(f"/tickets/{ticket['id']}").json()
    assert current == ticket
    assert current["status"] == "pending"
    assert current["external_id"] is None

    row = fetch_row(db_path, str(ticket["id"]))
    assert row is not None
    assert row["status"] == "pending"
    assert row["external_id"] is None


@pytest.mark.parametrize(
    ("failure_mode", "expected_status"),
    [
        (ProviderMode.TIMEOUT, 504),
        (ProviderMode.ERROR, 502),
    ],
)
def test_retry_after_failure_can_succeed(
    client: TestClient, provider, failure_mode: ProviderMode, expected_status: int
) -> None:
    ticket = create_ticket(client)
    provider.mode = failure_mode

    failed = client.post(f"/tickets/{ticket['id']}/send")
    assert failed.status_code == expected_status

    provider.mode = ProviderMode.SUCCESS
    retried = client.post(f"/tickets/{ticket['id']}/send")

    assert retried.status_code == 200
    assert retried.json()["status"] == "sent"
    assert retried.json()["external_id"] == f"ext_{ticket['id']}"
    assert provider.calls == [ticket["id"], ticket["id"]]


def test_second_send_is_sequential_idempotent(
    client: TestClient, provider, db_path: Path
) -> None:
    ticket = create_ticket(client)

    first = client.post(f"/tickets/{ticket['id']}/send")
    assert first.status_code == 200
    assert len(provider.calls) == 1

    second = client.post(f"/tickets/{ticket['id']}/send")

    assert second.status_code == 200
    assert second.json() == first.json()
    assert second.json()["external_id"] == first.json()["external_id"]
    assert provider.calls == [ticket["id"]]

    row = fetch_row(db_path, str(ticket["id"]))
    assert row is not None
    assert row["status"] == "sent"
    assert row["external_id"] == first.json()["external_id"]


def test_send_log_does_not_include_pii(
    client: TestClient, provider, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO, logger="abai.tickets")
    email = "send-private@example.com"
    description = "send-private-description"
    created = client.post(
        "/tickets",
        json={
            "subject": "send-private-subject",
            "description": description,
            "email": email,
        },
    )
    assert created.status_code == 201

    ticket_id = created.json()["id"]
    response = client.post(f"/tickets/{ticket_id}/send")

    assert response.status_code == 200
    assert "ticket_sent" in caplog.text
    assert ticket_id in caplog.text
    assert "result=sent" in caplog.text
    assert email not in caplog.text
    assert description not in caplog.text


def test_persistence_failure_does_not_return_success(
    app: FastAPI,
    provider,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with TestClient(app, raise_server_exceptions=False) as test_client:
        ticket = create_ticket(test_client)

        def fail_mark_sent(ticket_id: str, external_id: str) -> None:
            raise sqlite3.OperationalError("disk I/O error")

        monkeypatch.setattr(
            app.state.ticket_service.repository, "mark_sent", fail_mark_sent
        )
        response = test_client.post(f"/tickets/{ticket['id']}/send")

        assert response.status_code == 500
        assert provider.calls == [ticket["id"]]
        assert test_client.get(f"/tickets/{ticket['id']}").json() == ticket


def test_unexpected_provider_error_returns_500_not_502_or_504(
    db_path: Path,
) -> None:
    class UnexpectedProvider:
        def send(self, ticket_id: str) -> str:
            raise RuntimeError("unexpected provider error")

    app = create_app(db_path=db_path, provider=UnexpectedProvider())
    with TestClient(app, raise_server_exceptions=False) as test_client:
        ticket = create_ticket(test_client)
        response = test_client.post(f"/tickets/{ticket['id']}/send")

        assert response.status_code == 500
        assert response.status_code not in (502, 504)
        assert test_client.get(f"/tickets/{ticket['id']}").json() == ticket


def test_sent_state_survives_an_app_restart(db_path: Path) -> None:
    first_app = create_app(db_path=db_path, provider=MockProvider())
    with TestClient(first_app) as first_client:
        ticket = create_ticket(first_client)
        sent = first_client.post(f"/tickets/{ticket['id']}/send")
        assert sent.status_code == 200
        expected = sent.json()

    second_app = create_app(db_path=db_path, provider=MockProvider())
    with TestClient(second_app) as second_client:
        response = second_client.get(f"/tickets/{ticket['id']}")

    assert response.status_code == 200
    assert response.json() == expected
