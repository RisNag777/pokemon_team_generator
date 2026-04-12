"""SQLite persistence: trainer name, camera photo, team (per-letter slots), generated image."""

from __future__ import annotations

import json
import sqlite3
import string
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_DB_NAME = "trainer_teams.sqlite"

_UNSET: Any = object()


def db_path() -> Path:
    return Path(__file__).resolve().parent.parent / _DB_NAME


def _letters_a_to_z(raw: str) -> list[str]:
    return [c.upper() for c in raw if c.upper() in string.ascii_uppercase]


def _migrate_nullable_blobs(conn: sqlite3.Connection) -> None:
    """Allow NULL photo_blob / team_image_blob for incremental saves (older DBs had NOT NULL)."""
    info = conn.execute("PRAGMA table_info(trainer_teams)").fetchall()
    if not info:
        return
    need = False
    for col in info:
        name, notnull = col[1], col[3]
        if name in ("photo_blob", "team_image_blob") and notnull:
            need = True
            break
    if not need:
        return
    conn.execute("BEGIN")
    conn.execute(
        """
        CREATE TABLE trainer_teams_new (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            trainer_name TEXT NOT NULL,
            photo_blob BLOB,
            team_slugs_json TEXT NOT NULL,
            team_image_blob BLOB,
            created_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        INSERT INTO trainer_teams_new (id, trainer_name, photo_blob, team_slugs_json, team_image_blob, created_at)
        SELECT id, trainer_name, photo_blob, team_slugs_json, team_image_blob, created_at FROM trainer_teams
        """
    )
    conn.execute("DROP TABLE trainer_teams")
    conn.execute("ALTER TABLE trainer_teams_new RENAME TO trainer_teams")
    conn.commit()


def init_db() -> None:
    path = db_path()
    with sqlite3.connect(path) as conn:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS trainer_teams (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                trainer_name TEXT NOT NULL,
                photo_blob BLOB,
                team_slugs_json TEXT NOT NULL,
                team_image_blob BLOB,
                created_at TEXT NOT NULL
            )
            """
        )
        _migrate_nullable_blobs(conn)


def _parse_team_json(raw: str, *, trainer_name: str) -> list[list[str]]:
    """Return per-letter slot lists; supports v2 {\"version\":2,\"slots\":...} or legacy flat list."""
    try:
        j = json.loads(raw)
    except json.JSONDecodeError:
        return []
    if isinstance(j, dict) and j.get("version") == 2 and isinstance(j.get("slots"), list):
        return [[str(s) for s in slot] for slot in j["slots"]]
    if isinstance(j, list) and j and isinstance(j[0], str):
        return _legacy_flat_to_slots(j, trainer_name)
    if isinstance(j, list) and j and isinstance(j[0], list):
        return [[str(s) for s in slot] for slot in j]
    return []


def _legacy_flat_to_slots(flat: list[str], trainer_name: str) -> list[list[str]]:
    letters = _letters_a_to_z(trainer_name)
    n = len(letters)
    if n == 0:
        return []
    if len(flat) == n:
        return [[s] for s in flat]
    if len(flat) % n == 0:
        k = len(flat) // n
        return [flat[i * k : (i + 1) * k] for i in range(n)]
    out: list[list[str]] = [[] for _ in range(n)]
    out[0] = list(flat)
    return out


def list_saved_teams() -> list[dict[str, int | str]]:
    init_db()
    with sqlite3.connect(db_path()) as conn:
        cur = conn.execute(
            "SELECT id, trainer_name, created_at FROM trainer_teams ORDER BY id DESC"
        )
        rows = cur.fetchall()
    return [{"id": r[0], "trainer_name": r[1], "created_at": r[2]} for r in rows]


def get_trainer(row_id: int) -> dict[str, object]:
    init_db()
    with sqlite3.connect(db_path()) as conn:
        row = conn.execute(
            """
            SELECT id, trainer_name, photo_blob, team_slugs_json, team_image_blob, created_at
            FROM trainer_teams WHERE id = ?
            """,
            (row_id,),
        ).fetchone()
    if not row:
        raise KeyError(f"No trainer row {row_id}")
    team_slots = _parse_team_json(str(row[3]), trainer_name=str(row[1]))
    return {
        "id": int(row[0]),
        "trainer_name": str(row[1]),
        "photo_bytes": row[2],
        "team_slots": team_slots,
        "team_image_png": row[4],
        "created_at": str(row[5]),
    }


def _team_payload(team_slots: list[list[str]]) -> str:
    return json.dumps({"version": 2, "slots": team_slots})


def insert_draft_trainer(trainer_name: str, team_slots: list[list[str]]) -> int:
    """New row with team + name only; photo and image NULL until filled in."""
    init_db()
    created_at = datetime.now(timezone.utc).isoformat()
    payload = _team_payload(team_slots)
    with sqlite3.connect(db_path()) as conn:
        cur = conn.execute(
            """
            INSERT INTO trainer_teams (trainer_name, photo_blob, team_slugs_json, team_image_blob, created_at)
            VALUES (?, NULL, ?, NULL, ?)
            """,
            (trainer_name.strip(), payload, created_at),
        )
        conn.commit()
        row_id = cur.lastrowid
    assert row_id is not None
    return int(row_id)


def update_trainer_fields(
    row_id: int,
    *,
    trainer_name: str | None = None,
    team_slots: list[list[str]] | None = None,
    photo_bytes: Any = _UNSET,
    team_image_png: Any = _UNSET,
) -> None:
    """Update only columns that are passed (besides trainer_name/team_slots which use None to skip)."""
    init_db()
    parts: list[str] = []
    vals: list[object] = []
    if trainer_name is not None:
        parts.append("trainer_name = ?")
        vals.append(trainer_name.strip())
    if team_slots is not None:
        parts.append("team_slugs_json = ?")
        vals.append(_team_payload(team_slots))
    if photo_bytes is not _UNSET:
        parts.append("photo_blob = ?")
        vals.append(photo_bytes)
    if team_image_png is not _UNSET:
        parts.append("team_image_blob = ?")
        vals.append(team_image_png)
    if not parts:
        return
    vals.append(row_id)
    sql = f"UPDATE trainer_teams SET {', '.join(parts)} WHERE id = ?"
    with sqlite3.connect(db_path()) as conn:
        conn.execute(sql, vals)
        conn.commit()


def save_trainer_team(
    trainer_name: str,
    photo_bytes: bytes,
    team_slots: list[list[str]],
    team_image_png: bytes,
) -> int:
    """Insert a fully populated row; returns new primary key."""
    init_db()
    created_at = datetime.now(timezone.utc).isoformat()
    payload = _team_payload(team_slots)
    with sqlite3.connect(db_path()) as conn:
        cur = conn.execute(
            """
            INSERT INTO trainer_teams (trainer_name, photo_blob, team_slugs_json, team_image_blob, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                trainer_name.strip(),
                photo_bytes,
                payload,
                team_image_png,
                created_at,
            ),
        )
        conn.commit()
        row_id = cur.lastrowid
    assert row_id is not None
    return int(row_id)


def update_trainer_team(
    row_id: int,
    trainer_name: str,
    photo_bytes: bytes,
    team_slots: list[list[str]],
    team_image_png: bytes,
) -> None:
    """Overwrite all content columns (keeps id and original created_at)."""
    update_trainer_fields(
        row_id,
        trainer_name=trainer_name,
        team_slots=team_slots,
        photo_bytes=photo_bytes,
        team_image_png=team_image_png,
    )
