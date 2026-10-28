"""SQLite connection and schema initialisation.
"""

from __future__ import annotations

import os
import sqlite3
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

DEFAULT_DB_PATH = "tickets.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS tickets (
    id          TEXT PRIMARY KEY,
    subject     TEXT NOT NULL,
    description TEXT NOT NULL,
    email       TEXT NOT NULL,
    status      TEXT NOT NULL CHECK (status IN ('pending', 'sent')),
    created_at  TEXT NOT NULL,
    external_id TEXT,
    CHECK (
        (status = 'pending' AND external_id IS NULL)
        OR
        (status = 'sent' AND external_id IS NOT NULL)
    )
);
"""


def default_db_path() -> Path:
    """Return the configured database path (relative paths resolve from CWD)."""

    return Path(os.getenv("TICKETS_DB_PATH", DEFAULT_DB_PATH)).expanduser()


@contextmanager
def connect(db_path: str | Path) -> Generator[sqlite3.Connection, None, None]:
    """Open a SQLite connection and always close it when the block exits."""

    connection = sqlite3.connect(str(db_path), timeout=5.0)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA busy_timeout = 5000")
    try:
        yield connection
    finally:
        connection.close()


def init_db(db_path: str | Path | None = None) -> Path:
    """Create the database file and schema if they do not exist.

    Calling this more than once is safe because the table uses
    ``CREATE TABLE IF NOT EXISTS``. 
    """

    resolved_path = Path(db_path) if db_path is not None else default_db_path()
    resolved_path.parent.mkdir(parents=True, exist_ok=True)

    with connect(resolved_path) as connection:
        with connection:
            connection.execute(SCHEMA)

    return resolved_path
