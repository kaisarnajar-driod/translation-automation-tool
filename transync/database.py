"""SQLite-backed persistence for projects, sync history, and string snapshots."""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Generator

from transync.models.project import Project, SyncRecord, SyncStatus

_SCHEMA = """
CREATE TABLE IF NOT EXISTS projects (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    name            TEXT UNIQUE NOT NULL,
    repo_url        TEXT NOT NULL,
    local_path      TEXT NOT NULL,
    branch          TEXT NOT NULL DEFAULT 'main',
    strings_path    TEXT NOT NULL DEFAULT 'strings.xml',
    target_languages TEXT NOT NULL DEFAULT '[]',
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sync_history (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id      INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    status          TEXT NOT NULL,
    new_keys        INTEGER NOT NULL DEFAULT 0,
    modified_keys   INTEGER NOT NULL DEFAULT 0,
    removed_keys    INTEGER NOT NULL DEFAULT 0,
    languages_synced INTEGER NOT NULL DEFAULT 0,
    commit_sha      TEXT NOT NULL DEFAULT '',
    error_message   TEXT NOT NULL DEFAULT '',
    started_at      TEXT NOT NULL,
    finished_at     TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS string_snapshots (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id      INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    snapshot_json   TEXT NOT NULL,
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);
"""


class Database:
    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    @contextmanager
    def _connect(self) -> Generator[sqlite3.Connection, None, None]:
        conn = sqlite3.connect(str(self._db_path))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript(_SCHEMA)
            self._migrate(conn)

    @staticmethod
    def _migrate(conn: sqlite3.Connection) -> None:
        columns = {row["name"] for row in conn.execute("PRAGMA table_info(sync_history)").fetchall()}
        if "removed_keys" not in columns:
            conn.execute("ALTER TABLE sync_history ADD COLUMN removed_keys INTEGER NOT NULL DEFAULT 0")

    # ── Project CRUD ──────────────────────────────────────────────

    def add_project(self, project: Project) -> Project:
        with self._connect() as conn:
            cur = conn.execute(
                """INSERT INTO projects
                   (name, repo_url, local_path, branch, strings_path,
                    target_languages, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    project.name,
                    project.repo_url,
                    project.local_path,
                    project.branch,
                    project.strings_path,
                    json.dumps(project.target_languages),
                    project.created_at,
                    project.updated_at,
                ),
            )
            project.id = cur.lastrowid
        return project

    def remove_project(self, name: str) -> bool:
        with self._connect() as conn:
            cur = conn.execute("DELETE FROM projects WHERE name = ?", (name,))
            return cur.rowcount > 0

    def get_project(self, name: str) -> Project | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM projects WHERE name = ?", (name,)).fetchone()
        return self._row_to_project(row) if row else None

    def list_projects(self) -> list[Project]:
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM projects ORDER BY name").fetchall()
        return [self._row_to_project(r) for r in rows]

    @staticmethod
    def _row_to_project(row: sqlite3.Row) -> Project:
        return Project(
            id=row["id"],
            name=row["name"],
            repo_url=row["repo_url"],
            local_path=row["local_path"],
            branch=row["branch"],
            strings_path=row["strings_path"],
            target_languages=json.loads(row["target_languages"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    # ── Sync history ──────────────────────────────────────────────

    def add_sync_record(self, record: SyncRecord) -> SyncRecord:
        with self._connect() as conn:
            cur = conn.execute(
                """INSERT INTO sync_history
                   (project_id, status, new_keys, modified_keys, removed_keys,
                    languages_synced, commit_sha, error_message, started_at, finished_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    record.project_id,
                    record.status.value,
                    record.new_keys,
                    record.modified_keys,
                    record.removed_keys,
                    record.languages_synced,
                    record.commit_sha,
                    record.error_message,
                    record.started_at,
                    record.finished_at,
                ),
            )
            record.id = cur.lastrowid
        return record

    def update_sync_record(self, record: SyncRecord) -> None:
        with self._connect() as conn:
            conn.execute(
                """UPDATE sync_history SET
                   status=?, new_keys=?, modified_keys=?, removed_keys=?,
                   languages_synced=?, commit_sha=?, error_message=?, finished_at=?
                   WHERE id=?""",
                (
                    record.status.value,
                    record.new_keys,
                    record.modified_keys,
                    record.removed_keys,
                    record.languages_synced,
                    record.commit_sha,
                    record.error_message,
                    record.finished_at,
                    record.id,
                ),
            )

    def get_sync_history(self, project_id: int, limit: int = 20) -> list[SyncRecord]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM sync_history WHERE project_id = ? ORDER BY id DESC LIMIT ?",
                (project_id, limit),
            ).fetchall()
        return [self._row_to_sync(r) for r in rows]

    @staticmethod
    def _row_to_sync(row: sqlite3.Row) -> SyncRecord:
        return SyncRecord(
            id=row["id"],
            project_id=row["project_id"],
            status=SyncStatus(row["status"]),
            new_keys=row["new_keys"],
            modified_keys=row["modified_keys"],
            removed_keys=row["removed_keys"],
            languages_synced=row["languages_synced"],
            commit_sha=row["commit_sha"],
            error_message=row["error_message"],
            started_at=row["started_at"],
            finished_at=row["finished_at"],
        )

    # ── String snapshots ──────────────────────────────────────────

    def save_snapshot(self, project_id: int, strings: dict[str, str]) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO string_snapshots (project_id, snapshot_json) VALUES (?, ?)",
                (project_id, json.dumps(strings, ensure_ascii=False)),
            )

    def get_latest_snapshot(self, project_id: int) -> dict[str, str] | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT snapshot_json FROM string_snapshots WHERE project_id = ? ORDER BY id DESC LIMIT 1",
                (project_id,),
            ).fetchone()
        if row:
            return json.loads(row["snapshot_json"])
        return None
