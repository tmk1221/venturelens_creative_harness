"""Schema migrations and connection hygiene."""
from __future__ import annotations

from post_core.queue import db


def test_connect_creates_schema_and_is_idempotent(tmp_path):
    con = db.connect(tmp_path)
    try:
        tables = {
            row["name"]
            for row in con.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        assert {"job", "event", "budget"} <= tables
        assert con.execute("PRAGMA user_version").fetchone()[0] == db.SCHEMA_VERSION
    finally:
        con.close()

    # Reconnecting (e.g. a restart) must not fail or re-run migrations destructively.
    con2 = db.connect(tmp_path)
    try:
        assert con2.execute("PRAGMA user_version").fetchone()[0] == db.SCHEMA_VERSION
    finally:
        con2.close()


def test_open_db_closes_on_exception(tmp_path):
    with db.open_db(tmp_path) as con:
        con.execute("INSERT INTO budget (id, cap, spent, unit) VALUES ('b1', 10, 0, 'usd')")
        con.commit()

    try:
        with db.open_db(tmp_path) as con:
            con.execute("SELECT 1/0")
    except Exception:
        pass

    # The connection from the failed block is closed; a fresh one still works.
    with db.open_db(tmp_path) as con:
        row = con.execute("SELECT cap FROM budget WHERE id='b1'").fetchone()
        assert row["cap"] == 10


def test_db_path_lives_under_dot_post3(tmp_path):
    assert db.db_path(tmp_path) == tmp_path / ".post3" / "queue.db"
