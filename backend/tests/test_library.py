"""Tests for the main-library side: import_to_library + remove_from_inbox.

Pytest port of the full cycle scripts/validate-beets.sh used to prove:
catalog in inbox → import into main library with explicit tags → clean up
the inbox DB.  Runs real beets against temporary libraries.
"""
from __future__ import annotations

from pathlib import Path

from music_importer.config import Config
from music_importer.services import beets as beets_svc

from .conftest import library_files, main_db_items, place_album, place_standalone


def test_full_cycle_single_file(library_config: Config) -> None:
    """Catalog → import to main library → remove from inbox DB."""
    src = place_standalone(library_config)

    # 1. Catalog in the inbox library (no copy/move/write).
    result = beets_svc.catalog_path(library_config, src, autotag=False)
    assert result.returncode == 0, result.stderr
    assert str(src) in beets_svc.query_all_inbox_paths(library_config)

    # 2. Import into the main library using the inbox DB tags.
    tags = beets_svc.query_item_tags(library_config, src)
    result = beets_svc.import_to_library(library_config, src, tags)
    assert result.returncode == 0, (
        f"import_to_library failed:\nstdout: {result.stdout}\nstderr: {result.stderr}"
    )

    # File was copied into the library directory (source untouched).
    files = library_files(library_config)
    assert len(files) == 1, f"expected 1 library file, got: {files}"
    assert src.exists(), "source file must not be moved by a copy import"

    # Main DB has the item with the fixture's tags.
    items = main_db_items(library_config)
    assert len(items) == 1
    assert items[0]["title"] == "Standalone Track"
    assert items[0]["artist"] == "Solo Artist"
    assert items[0]["album"] == "Solo Single"

    # 3. Remove from the inbox DB (file deletion is the caller's job).
    result = beets_svc.remove_from_inbox(library_config, src)
    assert result.returncode == 0, result.stderr
    assert beets_svc.query_all_inbox_paths(library_config) == set()


def test_import_album_directory(library_config: Config) -> None:
    """An album directory imports as a whole: all tracks land in the library."""
    src = place_album(library_config)
    beets_svc.catalog_path(library_config, src, autotag=False)

    # Album-level tags only — per-track tags (title, track) must come from
    # the files themselves, not be stamped identically onto every track.
    tags = {"artist": "Inbox Artist", "album": "Inbox Album"}
    result = beets_svc.import_to_library(library_config, src, tags)
    assert result.returncode == 0, result.stderr

    files = library_files(library_config)
    assert len(files) == 3, f"expected 3 library files, got: {files}"

    items = main_db_items(library_config)
    assert len(items) == 3
    assert {i["title"] for i in items} == {"Opening", "Interlude", "Closing"}
    assert all(i["album"] == "Inbox Album" for i in items)

    # Cleanup removes all three inbox entries with one directory query.
    result = beets_svc.remove_from_inbox(library_config, src)
    assert result.returncode == 0, result.stderr
    assert beets_svc.query_all_inbox_paths(library_config) == set()


def test_import_set_tags_override_file_tags(library_config: Config) -> None:
    """--set tags win over the embedded file tags (user-confirmed tags rule)."""
    src = place_standalone(library_config)
    beets_svc.catalog_path(library_config, src, autotag=False)

    tags = {"title": "Renamed Track", "artist": "Renamed Artist", "album": "Renamed"}
    result = beets_svc.import_to_library(library_config, src, tags)
    assert result.returncode == 0, result.stderr

    items = main_db_items(library_config)
    assert len(items) == 1
    assert items[0]["title"] == "Renamed Track"
    assert items[0]["artist"] == "Renamed Artist"
    assert items[0]["album"] == "Renamed"


def test_import_mirrors_artist_to_albumartist(library_config: Config) -> None:
    """artist → albumartist mirroring so library paths use the right value."""
    src = place_standalone(library_config)
    beets_svc.catalog_path(library_config, src, autotag=False)

    result = beets_svc.import_to_library(library_config, src, {"artist": "Only Artist"})
    assert result.returncode == 0, result.stderr

    items = main_db_items(library_config)
    assert len(items) == 1
    assert items[0]["albumartist"] == "Only Artist"

    # The library path is organised under the albumartist.
    rel_parts = [p.relative_to(library_config.library_path or Path())
                 for p in library_files(library_config)]
    assert any("Only Artist" in str(p) for p in rel_parts), rel_parts
