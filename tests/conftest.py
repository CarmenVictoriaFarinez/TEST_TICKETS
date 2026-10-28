from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.main import create_app
from app.providers.mock_provider import MockProvider


class SpyProvider(MockProvider):
    """Mock provider that records calls for assertions."""

    def __init__(self, mode: str = "success") -> None:
        super().__init__(mode)
        self.calls: list[str] = []

    def send(self, ticket_id: str) -> str:
        self.calls.append(ticket_id)
        return super().send(ticket_id)


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    """Each test gets its own SQLite file, so tests cannot see each other."""

    return tmp_path / "tickets.db"


@pytest.fixture
def provider() -> SpyProvider:
    return SpyProvider()


@pytest.fixture
def app(db_path: Path, provider: SpyProvider) -> FastAPI:
    return create_app(db_path=db_path, provider=provider)


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    with TestClient(app) as test_client:
        yield test_client
