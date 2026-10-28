from __future__ import annotations

import pytest

from app.providers.mock_provider import (
    MockProvider,
    ProviderMode,
    ProviderTimeoutError,
    ProviderUnavailableError,
)


def test_success_returns_a_deterministic_external_id() -> None:
    provider = MockProvider(ProviderMode.SUCCESS)

    assert provider.send("ticket-1") == "ext_ticket-1"
    assert provider.send("ticket-1") == "ext_ticket-1"


def test_timeout_raises_its_specific_exception() -> None:
    provider = MockProvider(ProviderMode.TIMEOUT)

    with pytest.raises(ProviderTimeoutError):
        provider.send("ticket-1")


def test_error_raises_its_specific_exception() -> None:
    provider = MockProvider(ProviderMode.ERROR)

    with pytest.raises(ProviderUnavailableError):
        provider.send("ticket-1")


def test_invalid_mode_is_rejected_at_construction() -> None:
    with pytest.raises(ValueError):
        MockProvider("unknown")
