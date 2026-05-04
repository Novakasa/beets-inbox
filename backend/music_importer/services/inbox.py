"""Inbox directory scanner, sidecar parser, and file watcher."""
from __future__ import annotations

import json
import logging
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any, override

from watchdog.events import FileCreatedEvent, FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer
from watchdog.observers.api import BaseObserver

from ..config import Config
from ..models import InboxItem
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


# ── Scanner ───────────────────────────────────────────────────────────────────

def _build_item(
    config: Config,
    item_path: Path,
    category: str,
    is_group: bool,
    audio_files: list[Path],
) -> InboxItem:
    item_id = path_to_id(config.inbox_path, item_path)

    # Collect tags from beets DB (use first audio file for single or group)
    primary = audio_files[0] if audio_files else item_path
    tags: dict[str, Any] = beets_svc.query_item_tags(config, primary)

    # Enrich with sidecar (only for single files)
    sidecar_data: dict[str, str] = {}
    if not is_group:
        sidecar_data = _parse_sidecar(item_path)
        # Sidecar title fills gap but doesn't override a beets match
        if not tags.get("title") and sidecar_data.get("title"):
            tags["title"] = sidecar_data["title"]

    return InboxItem(
        id=item_id,
        category=category,
        path=str(item_path),
        is_group=is_group,
        files=[str(f) for f in sorted(audio_files)],
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
    )


def scan_inbox(config: Config) -> list[InboxItem]:
    """Walk inbox directory and return all items (singles + album groups)."""
    items: list[InboxItem] = []
    inbox = config.inbox_path

    if not inbox.exists():
        return items

    for category_dir in sorted(inbox.iterdir()):
        if not category_dir.is_dir():
            continue
        category = category_dir.name

        for entry in sorted(category_dir.iterdir()):
            if entry.is_file() and is_audio(entry):
                items.append(_build_item(config, entry, category, False, [entry]))
            elif entry.is_dir():
                audio_files = sorted(
                    f for f in entry.iterdir() if f.is_file() and is_audio(f)
                )
                if audio_files:
                    items.append(
                        _build_item(config, entry, category, True, audio_files)
                    )

    return items


def get_item(config: Config, item_id: str) -> InboxItem | None:
    """Look up a single inbox item by ID."""
    try:
        item_path = id_to_path(config.inbox_path, item_id)
    except Exception:
        return None

    if not item_path.exists():
        return None

    # Determine category from path structure
    try:
        rel = item_path.relative_to(config.inbox_path)
        category = rel.parts[0]
    except (ValueError, IndexError):
        return None

    if item_path.is_file() and is_audio(item_path):
        return _build_item(config, item_path, category, False, [item_path])
    elif item_path.is_dir():
        audio_files = sorted(
            f for f in item_path.iterdir() if f.is_file() and is_audio(f)
        )
        if audio_files:
            return _build_item(config, item_path, category, True, audio_files)

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
        logger.info("Cataloging new file: %s", path)
        result = beets_svc.catalog_path(self._config, path)
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
