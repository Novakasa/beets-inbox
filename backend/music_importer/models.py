"""Shared data models (Pydantic)."""
from __future__ import annotations

from pydantic import BaseModel

# ── Inbox ──────────────────────────────────────────────────────────────────────


class TrackInfo(BaseModel):
    """Per-track metadata for a file inside an album group."""
    id: str           # hex-encoded relative path (usable as PATCH target)
    path: str
    title: str | None = None
    artist: str | None = None
    albumartist: str | None = None
    genre: str | None = None
    year: int | None = None
    track: int | None = None


class InboxItem(BaseModel):
    """A single file or album group waiting in the inbox."""
    id: str                          # hex-encoded relative path
    category: str
    path: str                        # absolute path (file or directory)
    is_group: bool                   # True = album directory, False = single file
    files: list[str]                 # audio file paths (or [path] for singles)

    # True once every audio file has a row in the inbox beets DB.  False while
    # the Cataloger hasn't swept it yet — or its last catalog attempt failed,
    # in which case catalog_error says why.
    cataloged: bool = False
    catalog_error: str | None = None

    # Album-level tags — sourced from beets DB then enriched by sidecar
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

    # Per-track details for album groups (empty for single files)
    tracks: list[TrackInfo] = []


class TagUpdate(BaseModel):
    """Partial tag update sent to PATCH /api/inbox/{item_id}."""
    title: str | None = None
    artist: str | None = None
    album: str | None = None
    albumartist: str | None = None
    genre: str | None = None
    year: int | None = None
