"""Shared data models (Pydantic)."""
from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel

# ── Inbox ──────────────────────────────────────────────────────────────────────

class InboxItem(BaseModel):
    """A single file or album group waiting in the inbox."""
    id: str                          # hex-encoded relative path
    category: str
    path: str                        # absolute path (file or directory)
    is_group: bool                   # True = album directory, False = single file
    # audio file paths inside a group (or [path] for single)
    files: list[str]

    # False while beets is still cataloging (auto-tagging in background)
    cataloged: bool = False

    # Tags — sourced from beets DB then enriched by sidecar
    title: str | None = None
    artist: str | None = None
    album: str | None = None
    albumartist: str | None = None
    genre: str | None = None
    year: int | None = None
    track: int | None = None

    # Sidecar fields (from .info.json)
    source_url: str | None = None
    uploader: str | None = None
    upload_date: str | None = None


class ImportRequest(BaseModel):
    """User-confirmed tags for committing an inbox item."""
    title: str | None = None
    artist: str | None = None
    album: str | None = None
    albumartist: str | None = None
    genre: str | None = None
    year: int | None = None


# ── Jobs ───────────────────────────────────────────────────────────────────────

class JobStatus(StrEnum):
    pending = "pending"
    running = "running"
    success = "success"
    failed = "failed"


class Job(BaseModel):
    id: str
    status: JobStatus
    source_path: str
    category: str | None = None
    artist: str | None = None
    album: str | None = None
    genre: str | None = None
    log: str = ""
    created_at: datetime
    completed_at: datetime | None = None
