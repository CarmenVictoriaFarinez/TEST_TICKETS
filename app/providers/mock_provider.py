"""Deterministic in-process provider used instead of a real external service."""

from __future__ import annotations

from enum import StrEnum
from typing import Protocol


class ProviderError(Exception):
    """Base class for expected provider failures."""


class ProviderTimeoutError(ProviderError):
    """The provider did not answer in time."""


class ProviderUnavailableError(ProviderError):
    """The provider is currently unavailable."""


class ProviderMode(StrEnum):
    SUCCESS = "success"
    TIMEOUT = "timeout"
    ERROR = "error"


class TicketProvider(Protocol):
    def send(self, ticket_id: str) -> str:
        """Send a ticket and return the external identifier."""


class MockProvider:
    """Provider simulator controlled by a mode, without network calls or sleeps."""

    def __init__(self, mode: str | ProviderMode = ProviderMode.SUCCESS) -> None:
        self.mode = ProviderMode(mode)

    def send(self, ticket_id: str) -> str:
        if self.mode is ProviderMode.TIMEOUT:
            raise ProviderTimeoutError(f"Mock provider timed out for ticket {ticket_id}")
        if self.mode is ProviderMode.ERROR:
            raise ProviderUnavailableError(f"Mock provider unavailable for ticket {ticket_id}")

        # Deterministic on purpose: tests do not depend on random values.
        return f"ext_{ticket_id}"
