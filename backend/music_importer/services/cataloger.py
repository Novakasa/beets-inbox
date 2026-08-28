"""Reconciling cataloger for the inbox scratchpad library.

The Cataloger owns cataloging.  Its interface is an idempotent sync():
reconcile the inbox directory against the inbox beets DB in both
directions —

- catalog every inbox item with audio files missing from the DB, once all
  its files have been stable for the stability window (a partially
  cataloged album group is removed and re-imported as a unit so beets
  keeps album semantics),
- prune DB rows whose file no longer exists on disk,
- remember the last catalog error per item, cleared on success.

There are no filesystem events: start() runs a sweep immediately and then
on a fixed interval, so a missed arrival is at worst one interval late and
never stuck.
"""
from __future__ import annotations

import logging
import threading
import time
from pathlib import Path

from ..config import Config
from ..models import InboxItem
from . import beets as beets_svc
from . import inbox as inbox_svc

logger = logging.getLogger(__name__)

_SWEEP_INTERVAL_SECS = 30.0
_STABILITY_SECS = 30.0


class Cataloger:
    """Keeps the inbox beets DB in sync with the inbox directory."""

    _config: Config
    _interval: float
    _stability: float
    _errors: dict[str, str]
    _errors_lock: threading.Lock
    _stop_event: threading.Event
    _thread: threading.Thread | None

    def __init__(
        self,
        config: Config,
        *,
        interval: float = _SWEEP_INTERVAL_SECS,
        stability: float = _STABILITY_SECS,
    ) -> None:
        self._config = config
        self._interval = interval
        self._stability = stability
        self._errors = {}
        self._errors_lock = threading.Lock()
        self._stop_event = threading.Event()
        self._thread = None

    # ── Sweep ─────────────────────────────────────────────────────────────────

    def sync(self) -> None:
        """One reconciliation sweep.  Idempotent; safe to call at any time."""
        config = self._config
        if not config.inbox_path.exists():
            return

        db_paths = beets_svc.query_all_inbox_paths(config)

        # Reverse: prune DB rows whose file vanished from disk.
        for path_str in sorted(db_paths):
            if not Path(path_str).exists():
                logger.info("Pruning vanished file from inbox DB: %s", path_str)
                beets_svc.remove_from_inbox(config, Path(path_str))
                db_paths.discard(path_str)

        # Forward: catalog items with files missing from the DB.
        cataloged_now: list[InboxItem] = []
        for item in inbox_svc.scan_inbox(config):
            files = [Path(f) for f in item.files]
            if all(str(f) in db_paths for f in files):
                self._clear_error(item.path)
                continue
            if not self._stable(files):
                continue

            item_path = Path(item.path)
            if any(str(f) in db_paths for f in files):
                # Partially cataloged album group: re-import as a unit so
                # beets keeps album grouping and no duplicate rows pile up.
                logger.info("Re-cataloging partial item: %s", item_path)
                beets_svc.remove_from_inbox(config, item_path)

            logger.info("Cataloging: %s", item_path)
            result = beets_svc.catalog_path(
                config, item_path, autotag=config.autotag
            )
            if result.returncode != 0:
                detail = result.stderr.strip() or result.stdout.strip() or "unknown"
                self._set_error(
                    item.path,
                    f"beet import failed (rc={result.returncode}): "
                    f"{detail.splitlines()[-1]}",
                )
            else:
                cataloged_now.append(item)

        # beets can exit 0 while skipping files it cannot read, so verify the
        # cataloged items actually landed in the DB and surface the ones that
        # did not.
        if cataloged_now:
            db_after = beets_svc.query_all_inbox_paths(config)
            for item in cataloged_now:
                skipped = [f for f in item.files if f not in db_after]
                if skipped:
                    names = ", ".join(Path(f).name for f in skipped)
                    self._set_error(item.path, f"beets did not catalog: {names}")
                else:
                    self._clear_error(item.path)

    def _stable(self, files: list[Path]) -> bool:
        """True when every file's mtime is older than the stability window."""
        now = time.time()
        try:
            return all(now - f.stat().st_mtime >= self._stability for f in files)
        except OSError:
            # A file vanished mid-sweep; the next sweep reconciles it.
            return False

    # ── Catalog errors ────────────────────────────────────────────────────────

    def catalog_errors(self) -> dict[str, str]:
        """{item path: last catalog error} for items whose last attempt failed."""
        with self._errors_lock:
            return dict(self._errors)

    def _set_error(self, item_path: str, message: str) -> None:
        with self._errors_lock:
            self._errors[item_path] = message

    def _clear_error(self, item_path: str) -> None:
        with self._errors_lock:
            _ = self._errors.pop(item_path, None)

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def start(self) -> None:
        """Sweep now and then every interval, until stop()."""
        if not self._config.inbox_path.exists():
            logger.warning(
                "Inbox path %s does not exist — sweeps will no-op until it does",
                self._config.inbox_path,
            )
        self._thread = threading.Thread(
            target=self._loop, daemon=True, name="cataloger"
        )
        self._thread.start()
        logger.info(
            "Cataloger started on %s (every %.0fs)",
            self._config.inbox_path, self._interval,
        )

    def _loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                self.sync()
            except Exception:
                logger.exception("Cataloger sweep failed")
            _ = self._stop_event.wait(timeout=self._interval)

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread is not None:
            # A sweep may sit in a long beet subprocess; the thread is a
            # daemon, so cap how long shutdown waits on it.
            self._thread.join(timeout=5.0)
        logger.info("Cataloger stopped")
