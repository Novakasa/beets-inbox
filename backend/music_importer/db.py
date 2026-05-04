"""SQLite job tracking (stdlib sqlite3)."""
from __future__ import annotations

import sqlite3
from collections.abc import Generator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from .models import Job, JobStatus

_CREATE_JOBS = """
CREATE TABLE IF NOT EXISTS jobs (
    id          TEXT PRIMARY KEY,
    status      TEXT NOT NULL,
    source_path TEXT NOT NULL,
    category    TEXT,
    artist      TEXT,
    album       TEXT,
    genre       TEXT,
    log         TEXT NOT NULL DEFAULT '',
    created_at  TEXT NOT NULL,
    completed_at TEXT
);
"""


@contextmanager
def _conn(db_path: Path) -> Generator[sqlite3.Connection, None, None]:
    con = sqlite3.connect(str(db_path))
    con.row_factory = sqlite3.Row
    try:
        yield con
        con.commit()
    finally:
        con.close()


def init_db(db_path: Path) -> None:
    with _conn(db_path) as con:
        con.executescript(_CREATE_JOBS)


def create_job(
    db_path: Path,
    source_path: str,
    category: str | None = None,
    artist: str | None = None,
    album: str | None = None,
    genre: str | None = None,
) -> Job:
    job = Job(
        id=str(uuid4()),
        status=JobStatus.pending,
        source_path=source_path,
        category=category,
        artist=artist,
        album=album,
        genre=genre,
        created_at=datetime.now(UTC),
    )
    with _conn(db_path) as con:
        con.execute(
            "INSERT INTO jobs"
            " (id, status, source_path, category, artist, album, genre, log,"
            " created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                job.id, job.status.value, job.source_path,
                job.category, job.artist, job.album, job.genre,
                job.log, job.created_at.isoformat(),
            ),
        )
    return job


def update_job(
    db_path: Path,
    job_id: str,
    status: JobStatus,
    log: str = "",
    completed_at: datetime | None = None,
) -> None:
    with _conn(db_path) as con:
        con.execute(
            """UPDATE jobs SET status=?, log=?, completed_at=? WHERE id=?""",
            (
                status.value,
                log,
                completed_at.isoformat() if completed_at else None,
                job_id,
            ),
        )


def append_job_log(db_path: Path, job_id: str, text: str) -> None:
    with _conn(db_path) as con:
        con.execute(
            "UPDATE jobs SET log = log || ? WHERE id = ?",
            (text, job_id),
        )


def get_job(db_path: Path, job_id: str) -> Job | None:
    with _conn(db_path) as con:
        row = con.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
    if row is None:
        return None
    return _row_to_job(row)


def list_jobs(db_path: Path, limit: int = 100) -> list[Job]:
    with _conn(db_path) as con:
        rows = con.execute(
            "SELECT * FROM jobs ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
    return [_row_to_job(r) for r in rows]


def _row_to_job(row: sqlite3.Row) -> Job:
    return Job(
        id=row["id"],
        status=JobStatus(row["status"]),
        source_path=row["source_path"],
        category=row["category"],
        artist=row["artist"],
        album=row["album"],
        genre=row["genre"],
        log=row["log"] or "",
        created_at=datetime.fromisoformat(row["created_at"]),
        completed_at=(
            datetime.fromisoformat(row["completed_at"]) if row["completed_at"] else None
        ),
    )
