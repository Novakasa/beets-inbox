"""Inbox directory scanner, sidecar parser, and file watcher."""
from __future__ import annotations

import contextlib
import json
import logging
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any, override

import mutagen
import mutagen._file
from watchdog.events import FileCreatedEvent, FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer
from watchdog.observers.api import BaseObserver

from ..config import Config
from ..models import InboxItem, TrackInfo
from . import beets as beets_svc

logger = logging.getLogger(__name__)

AUDIO_EXTENSIONS = frozenset(
    {".mp3", ".flac", ".wav", ".aac", ".ogg", ".m4a", ".opus", ".wv", ".ape"}
)

# File must be stable for this many seconds before cataloging.
_STABILITY_SECS = 3.0


def is_audio(path: Path) -> bool:
    return path.suffix.lower() in AUDIO_EXTENSIONS


# ── Item ID ───────────────────────────────────────────────────────────────────

def path_to_id(inbox_path: Path, item_path: Path) -> str:
    """Stable, reversible ID: hex-encoded relative path."""
    rel = item_path.relative_to(inbox_path)
    return rel.as_posix().encode().hex()


def id_to_path(inbox_path: Path, item_id: str) -> Path:
    rel = bytes.fromhex(item_id).decode()
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


# ── Tag reader ───────────────────────────────────────────────────────────────

def _read_file_tags(path: Path) -> dict[str, Any]:
    """Read embedded tags directly from an audio file using mutagen.

    Returns a dict with keys: title, artist, album, albumartist, genre, year,
    track.  Works immediately — no beets cataloging required.
    """
    try:
        audio = mutagen._file.File(str(path), easy=True)  # noqa: SLF001
    except Exception:
        return {}
    if audio is None or not audio.tags:
        return {}

    def first(key: str) -> str | None:
        vals = audio.tags.get(key)  # type: ignore[union-attr]
        return str(vals[0]) if vals else None

    result: dict[str, Any] = {}
    for src, dst in [
        ("title", "title"),
        ("artist", "artist"),
        ("album", "album"),
        ("albumartist", "albumartist"),
        ("genre", "genre"),
    ]:
        val = first(src)
        if val:
            result[dst] = val

    # date/tracknumber need normalisation
    date = first("date")
    if date:
        result["year"] = date[:4]  # "2024-01-01" → "2024"

    tracknum = first("tracknumber")
    if tracknum:
        with contextlib.suppress(ValueError):
            result["track"] = int(tracknum.split("/")[0])

    return result


# ── Scanner ───────────────────────────────────────────────────────────────────

def _build_item(
    config: Config,
    item_path: Path,
    category: str,
    is_group: bool,
    audio_files: list[Path],
    all_tags: dict[str, dict[str, Any]],
) -> InboxItem:
    item_id = path_to_id(config.inbox_path, item_path)
    primary = audio_files[0] if audio_files else item_path

    # Item is cataloged once beets has processed it and stored it in the DB.
    primary_key = str(primary)
    cataloged = primary_key in all_tags
    tags: dict[str, Any] = all_tags.get(primary_key, {})

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


def scan_inbox(config: Config) -> list[InboxItem]:
    """Walk inbox directory and return all items (singles + album groups)."""
    items: list[InboxItem] = []
    inbox = config.inbox_path

    if not inbox.exists():
        return items

    # One DB query for the whole inbox; every _build_item call shares the result.
    all_tags = beets_svc.query_all_inbox_tags(config)

    def mk(path: Path, cat: str, group: bool, files: list[Path]) -> InboxItem:
        return _build_item(config, path, cat, group, files, all_tags)

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


def get_item(config: Config, item_id: str) -> InboxItem | None:
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

    def mk(path: Path, group: bool, files: list[Path]) -> InboxItem:
        return _build_item(config, path, category, group, files, all_tags)

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


# ── Watcher ───────────────────────────────────────────────────────────────────

OnNewFile = Callable[[Path], None]


class _InboxEventHandler(FileSystemEventHandler):
    _on_new_file: OnNewFile
    _pending: dict[str, float]
    _lock: threading.Lock

    def __init__(self, on_new_file: OnNewFile) -> None:
        self._on_new_file = on_new_file
        self._pending = {}
        self._lock = threading.Lock()

    @override
    def on_created(self, event: FileSystemEvent) -> None:
        if isinstance(event, FileCreatedEvent) and not event.is_directory:
            path = Path(str(event.src_path))
            if is_audio(path):
                self._schedule(path)

    def _schedule(self, path: Path) -> None:
        with self._lock:
            self._pending[str(path)] = time.monotonic()

    def flush_stable(self) -> None:
        """Called periodically; fires callback for files that haven't changed."""
        now = time.monotonic()
        to_fire: list[Path] = []
        with self._lock:
            for path_str, queued_at in list(self._pending.items()):
                p = Path(path_str)
                if not p.exists():
                    del self._pending[path_str]
                    continue
                if now - queued_at >= _STABILITY_SECS:
                    to_fire.append(p)
                    del self._pending[path_str]
        for path in to_fire:
            try:
                self._on_new_file(path)
            except Exception:
                logger.exception("Error cataloging %s", path)


class InboxWatcher:
    """Watches the inbox directory and catalogs new audio files via beets."""

    _config: Config
    _observer: BaseObserver | None
    _handler: _InboxEventHandler | None
    _flush_thread: threading.Thread | None
    _stop_event: threading.Event

    def __init__(self, config: Config) -> None:
        self._config = config
        self._observer = None
        self._handler = None
        self._flush_thread = None
        self._stop_event = threading.Event()

    def _on_new_file(self, path: Path) -> None:
        if not path.exists():
            # File was deleted before the debounce fired (e.g. already imported).
            return
        # Files inside album subdirectories (inbox/category/album/track.flac) are
        # cataloged at the directory level by the upload endpoint.  Skip them here
        # to avoid conflicting singleton imports.
        try:
            rel = path.relative_to(self._config.inbox_path)
        except ValueError:
            return
        if len(rel.parts) > 2:
            return
        logger.info("Cataloging new file: %s", path)
        result = beets_svc.catalog_path(
            self._config, path, autotag=self._config.autotag
        )
        if result.returncode != 0:
            logger.warning(
                "beet import returned %d: %s", result.returncode, result.stderr
            )

    def _flush_loop(self) -> None:
        while not self._stop_event.is_set():
            if self._handler:
                self._handler.flush_stable()
            self._stop_event.wait(timeout=1.0)

    def start(self) -> None:
        if not self._config.inbox_path.exists():
            logger.warning(
                "Inbox path %s does not exist — watcher not started",
                self._config.inbox_path,
            )
            return

        self._handler = _InboxEventHandler(self._on_new_file)
        self._observer = Observer()
        _ = self._observer.schedule(
            self._handler, str(self._config.inbox_path), recursive=True
        )
        self._observer.start()

        self._flush_thread = threading.Thread(target=self._flush_loop, daemon=True)
        self._flush_thread.start()
        logger.info("Inbox watcher started on %s", self._config.inbox_path)

    def stop(self) -> None:
        self._stop_event.set()
        if self._observer:
            self._observer.stop()
            self._observer.join()
        logger.info("Inbox watcher stopped")
