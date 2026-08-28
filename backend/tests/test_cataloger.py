"""Cataloger tests — all behavior through sync(), plus one thread smoke test.

Real beets subprocesses against tmp_path inboxes, same as the rest of the
suite.  No lifespan, no events: sync() is the interface.
"""
from __future__ import annotations

import os
import shutil
import sqlite3
import time
from pathlib import Path

from music_importer.api import inbox as inbox_api
from music_importer.config import Config
from music_importer.services import beets as beets_svc
from music_importer.services import inbox as inbox_svc
from music_importer.services.cataloger import Cataloger

from .conftest import _STANDALONE, make_client, place_album, place_standalone


def _sweeper(config: Config, stability: float = 0.0) -> Cataloger:
    return Cataloger(config, stability=stability)


def _inbox_row_count(config: Config) -> int:
    con = sqlite3.connect(str(config.beets_inbox_db))
    try:
        return int(con.execute("SELECT COUNT(*) FROM items").fetchone()[0])
    finally:
        con.close()


def _age(path: Path, seconds: float = 7200.0) -> None:
    """Push a file's mtime into the past so it counts as stable."""
    past = time.time() - seconds
    os.utime(path, (past, past))


# ── Forward reconciliation ────────────────────────────────────────────────────

def test_sync_catalogs_standalone(inbox_config: Config) -> None:
    flac = place_standalone(inbox_config)

    _sweeper(inbox_config).sync()

    assert str(flac) in beets_svc.query_all_inbox_paths(inbox_config)
    (item,) = inbox_svc.scan_inbox(inbox_config)
    assert item.cataloged


def test_sync_catalogs_album_as_group(inbox_config: Config) -> None:
    album = place_album(inbox_config)
    audio_files = sorted(f for f in album.iterdir() if inbox_svc.is_audio(f))

    _sweeper(inbox_config).sync()

    db_paths = beets_svc.query_all_inbox_paths(inbox_config)
    assert {str(f) for f in audio_files} <= db_paths
    (item,) = inbox_svc.scan_inbox(inbox_config)
    assert item.is_group
    assert item.cataloged


def test_sync_is_idempotent(inbox_config: Config) -> None:
    place_standalone(inbox_config)
    sweeper = _sweeper(inbox_config)

    sweeper.sync()
    sweeper.sync()

    assert _inbox_row_count(inbox_config) == 1


def test_part_file_ignored_until_renamed(inbox_config: Config) -> None:
    """The yt-dlp repro: download to *.part, then rename to the final name."""
    final = place_standalone(inbox_config)
    part = final.with_name(final.name + ".part")
    final.rename(part)
    sweeper = _sweeper(inbox_config)

    sweeper.sync()
    assert beets_svc.query_all_inbox_paths(inbox_config) == set()

    part.rename(final)
    sweeper.sync()
    assert str(final) in beets_svc.query_all_inbox_paths(inbox_config)


def test_unstable_file_waits_for_stability_window(inbox_config: Config) -> None:
    flac = place_standalone(inbox_config)
    os.utime(flac)  # freshly written
    sweeper = _sweeper(inbox_config, stability=3600.0)

    sweeper.sync()
    assert beets_svc.query_all_inbox_paths(inbox_config) == set()

    _age(flac)
    sweeper.sync()
    assert str(flac) in beets_svc.query_all_inbox_paths(inbox_config)


def test_partial_group_recataloged_as_unit(inbox_config: Config) -> None:
    album = place_album(inbox_config)
    audio_files = sorted(f for f in album.iterdir() if inbox_svc.is_audio(f))

    # Simulate a half-finished catalog: only the first track made it in.
    result = beets_svc.catalog_path(inbox_config, audio_files[0], autotag=False)
    assert result.returncode == 0
    assert _inbox_row_count(inbox_config) == 1

    _sweeper(inbox_config).sync()

    db_paths = beets_svc.query_all_inbox_paths(inbox_config)
    assert {str(f) for f in audio_files} <= db_paths
    # Re-imported as a unit: no duplicate rows from the earlier partial pass.
    assert _inbox_row_count(inbox_config) == len(audio_files)


# ── Reverse reconciliation ────────────────────────────────────────────────────

def test_vanished_file_pruned_from_db(inbox_config: Config) -> None:
    flac = place_standalone(inbox_config)
    sweeper = _sweeper(inbox_config)
    sweeper.sync()
    assert str(flac) in beets_svc.query_all_inbox_paths(inbox_config)

    flac.unlink()
    sweeper.sync()

    assert beets_svc.query_all_inbox_paths(inbox_config) == set()


# ── Failure surfacing ─────────────────────────────────────────────────────────

def test_uncatalogable_file_gets_error_then_recovers(inbox_config: Config) -> None:
    bad = inbox_config.inbox_path / "unsorted" / "broken.flac"
    bad.parent.mkdir(parents=True, exist_ok=True)
    _ = bad.write_bytes(b"this is not audio")
    sweeper = _sweeper(inbox_config)

    sweeper.sync()

    errors = sweeper.catalog_errors()
    assert str(bad) in errors
    (item,) = inbox_svc.scan_inbox(inbox_config, errors)
    assert not item.cataloged
    assert item.catalog_error is not None

    # Replace with a readable file at the same path: next sweep recovers.
    shutil.copy(_STANDALONE, bad)
    sweeper.sync()

    assert sweeper.catalog_errors() == {}
    (item,) = inbox_svc.scan_inbox(inbox_config, sweeper.catalog_errors())
    assert item.cataloged
    assert item.catalog_error is None


def test_catalog_error_surfaces_in_api(inbox_config: Config) -> None:
    flac = place_standalone(inbox_config)
    client = make_client(inbox_config)
    client.app.dependency_overrides[inbox_api._catalog_errors] = (  # noqa: SLF001
        lambda: {str(flac): "beet import failed (rc=1): boom"}
    )

    items = client.get("/api/inbox").json()

    assert items[0]["catalog_error"] == "beet import failed (rc=1): boom"


# ── Lifecycle smoke test ──────────────────────────────────────────────────────

def test_start_stop_runs_sweeps(inbox_config: Config) -> None:
    flac = place_standalone(inbox_config)
    cataloger = Cataloger(inbox_config, interval=0.2, stability=0.0)

    cataloger.start()
    try:
        deadline = time.monotonic() + 15.0
        while time.monotonic() < deadline:
            if str(flac) in beets_svc.query_all_inbox_paths(inbox_config):
                break
            time.sleep(0.1)
        else:
            raise AssertionError("file was not cataloged by the running sweep")
    finally:
        cataloger.stop()
