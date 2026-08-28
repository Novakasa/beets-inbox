"""Inbox directory scanner and sidecar parser."""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from ..config import Config
from ..models import InboxItem, TrackInfo
from . import beets as beets_svc

logger = logging.getLogger(__name__)

AUDIO_EXTENSIONS = frozenset(
    {".mp3", ".flac", ".wav", ".aac", ".ogg", ".m4a", ".opus", ".wv", ".ape"}
)


def is_audio(path: Path) -> bool:
    return path.suffix.lower() in AUDIO_EXTENSIONS


# ── Item ID ───────────────────────────────────────────────────────────────────

def path_to_id(inbox_path: Path, item_path: Path) -> str:
    """Stable, reversible ID: hex-encoded relative path."""
    rel = item_path.relative_to(inbox_path)
    return rel.as_posix().encode().hex()


def id_to_path(inbox_path: Path, item_id: str) -> Path:
    rel = Path(bytes.fromhex(item_id).decode())
    # A crafted ID must not address anything outside the inbox.
    if rel.is_absolute() or ".." in rel.parts:
        raise ValueError(f"item id escapes the inbox: {item_id}")
    return inbox_path / rel


# ── Sidecar parsing ───────────────────────────────────────────────────────────

def _parse_sidecar(audio_path: Path) -> dict[str, str]:
    """Parse a yt-dlp .info.json sidecar file alongside an audio file."""
    sidecar = audio_path.with_suffix(audio_path.suffix + ".info.json")
    if not sidecar.exists():
        return {}
    try:
        data: dict[str, Any] = json.loads(sidecar.read_text())
        result: dict[str, str] = {}
        uploader: str | None = data.get("uploader") or data.get("channel")
        if uploader:
            result["uploader"] = uploader
        title: str | None = data.get("title")
        if title:
            result["title"] = title
        url: str | None = data.get("webpage_url") or data.get("original_url")
        if url:
            result["source_url"] = url
        upload_date: str | None = data.get("upload_date")
        if upload_date:
            # yt-dlp format: YYYYMMDD
            d = str(upload_date)
            if len(d) == 8:
                result["upload_date"] = f"{d[:4]}-{d[4:6]}-{d[6:]}"
            else:
                result["upload_date"] = d
        return result
    except Exception:
        logger.exception("Failed to parse sidecar %s", sidecar)
        return {}


# ── Scanner ───────────────────────────────────────────────────────────────────

def _build_item(
    config: Config,
    item_path: Path,
    category: str,
    is_group: bool,
    audio_files: list[Path],
    all_tags: dict[str, dict[str, Any]],
    catalog_errors: dict[str, str],
) -> InboxItem:
    item_id = path_to_id(config.inbox_path, item_path)
    primary = audio_files[0] if audio_files else item_path

    # Cataloged once beets has processed every audio file into the inbox DB.
    cataloged = bool(audio_files) and all(str(f) in all_tags for f in audio_files)
    tags: dict[str, Any] = all_tags.get(str(primary), {})

    # Enrich with sidecar (only for single files)
    sidecar_data: dict[str, str] = {}
    if not is_group:
        sidecar_data = _parse_sidecar(item_path)
        if not tags.get("title") and sidecar_data.get("title"):
            tags["title"] = sidecar_data["title"]

    # Build per-track list for album groups.
    tracks: list[TrackInfo] = []
    if is_group:
        for f in audio_files:
            f_tags = all_tags.get(str(f), {})
            tracks.append(TrackInfo(
                id=path_to_id(config.inbox_path, f),
                path=str(f),
                title=f_tags.get("title"),
                artist=f_tags.get("artist"),
                albumartist=f_tags.get("albumartist"),
                genre=f_tags.get("genre"),
                year=f_tags.get("year"),
                track=f_tags.get("track"),
            ))

    return InboxItem(
        id=item_id,
        category=category,
        path=str(item_path),
        is_group=is_group,
        files=[str(f) for f in sorted(audio_files)],
        cataloged=cataloged,
        catalog_error=catalog_errors.get(str(item_path)),
        title=tags.get("title"),
        artist=tags.get("artist"),
        album=tags.get("album"),
        albumartist=tags.get("albumartist"),
        genre=tags.get("genre"),
        year=tags.get("year"),
        track=tags.get("track"),
        source_url=sidecar_data.get("source_url"),
        uploader=sidecar_data.get("uploader"),
        upload_date=sidecar_data.get("upload_date"),
        tracks=tracks,
    )


def scan_inbox(
    config: Config, catalog_errors: dict[str, str] | None = None
) -> list[InboxItem]:
    """Walk inbox directory and return all items (singles + album groups)."""
    items: list[InboxItem] = []
    inbox = config.inbox_path
    errors = catalog_errors or {}

    if not inbox.exists():
        return items

    # One DB query for the whole inbox; every _build_item call shares the result.
    all_tags = beets_svc.query_all_inbox_tags(config)

    def mk(path: Path, cat: str, group: bool, files: list[Path]) -> InboxItem:
        return _build_item(config, path, cat, group, files, all_tags, errors)

    for category_dir in sorted(inbox.iterdir()):
        if not category_dir.is_dir():
            continue
        category = category_dir.name

        for entry in sorted(category_dir.iterdir()):
            if entry.is_file() and is_audio(entry):
                items.append(mk(entry, category, False, [entry]))
            elif entry.is_dir():
                audio_files = sorted(
                    f for f in entry.iterdir() if f.is_file() and is_audio(f)
                )
                if audio_files:
                    items.append(mk(entry, category, True, audio_files))

    return items


def get_item(
    config: Config, item_id: str, catalog_errors: dict[str, str] | None = None
) -> InboxItem | None:
    """Look up a single inbox item by ID."""
    try:
        item_path = id_to_path(config.inbox_path, item_id)
    except Exception:
        return None

    if not item_path.exists():
        return None

    try:
        rel = item_path.relative_to(config.inbox_path)
        category = rel.parts[0]
    except (ValueError, IndexError):
        return None

    all_tags = beets_svc.query_all_inbox_tags(config)
    errors = catalog_errors or {}

    def mk(path: Path, group: bool, files: list[Path]) -> InboxItem:
        return _build_item(config, path, category, group, files, all_tags, errors)

    if item_path.is_file() and is_audio(item_path):
        return mk(item_path, False, [item_path])
    elif item_path.is_dir():
        audio_files = sorted(
            f for f in item_path.iterdir() if f.is_file() and is_audio(f)
        )
        if audio_files:
            return mk(item_path, True, audio_files)

    return None


def list_categories(config: Config) -> list[str]:
    """Return category subdirectory names."""
    if not config.inbox_path.exists():
        return []
    return sorted(d.name for d in config.inbox_path.iterdir() if d.is_dir())
