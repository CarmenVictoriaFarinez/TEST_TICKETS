"""Application entry point and composition root."""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.api.tickets import router
from app.db import default_db_path, init_db
from app.providers.mock_provider import (
    MockProvider,
    ProviderTimeoutError,
    ProviderUnavailableError,
    TicketProvider,
)
from app.repositories.ticket_repository import TicketRepository
from app.services.ticket_service import TicketNotFoundError, TicketService


def create_app(
    db_path: str | Path | None = None,
    provider: TicketProvider | None = None,
) -> FastAPI:
    """Build the app with an isolated database path and provider when requested."""

    resolved_db_path = Path(db_path) if db_path is not None else default_db_path()
    init_db(resolved_db_path)

    if provider is None:
        provider = MockProvider(os.getenv("PROVIDER_MODE", "success"))

    app = FastAPI(title="ABAI Tickets API", version="1.0.0")
    app.state.db_path = resolved_db_path
    app.state.provider = provider
    app.state.ticket_service = TicketService(
        TicketRepository(resolved_db_path), provider
    )
    app.include_router(router)

    @app.exception_handler(TicketNotFoundError)
    async def ticket_not_found_handler(
        request: Request, exc: TicketNotFoundError
    ) -> JSONResponse:
        return JSONResponse(status_code=404, content={"detail": "Ticket not found"})

    @app.exception_handler(ProviderTimeoutError)
    async def provider_timeout_handler(
        request: Request, exc: ProviderTimeoutError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=504, content={"detail": "Provider timed out"}
        )

    @app.exception_handler(ProviderUnavailableError)
    async def provider_unavailable_handler(
        request: Request, exc: ProviderUnavailableError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=502, content={"detail": "Provider unavailable"}
        )

    return app


app = create_app()
