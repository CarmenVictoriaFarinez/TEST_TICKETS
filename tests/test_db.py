import sqlite3

from app.main import create_app


def test_create_app_initializes_database(tmp_path):
    db_path = tmp_path / "fresh_tickets.db"

    assert not db_path.exists()

    create_app(db_path)

    assert db_path.exists()

    with sqlite3.connect(db_path) as connection:
        result = connection.execute("""
            SELECT name
            FROM sqlite_master
            WHERE type = 'table'
              AND name = 'tickets'
        """).fetchone()

    assert result is not None