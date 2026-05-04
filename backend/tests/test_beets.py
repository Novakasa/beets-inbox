"""Tests for the beets service layer — catalog, path matching, tag reading."""
from __future__ import annotations

from pathlib import Path

from music_importer.config import Config
from music_importer.services import beets as beets_svc


def test_catalog_creates_db_entry(inbox_config: Config, standalone_flac: Path) -> None:
    """catalog_path stores the file in the beets DB."""
    result = beets_svc.catalog_path(inbox_config, standalone_flac, autotag=False)
    assert result.returncode == 0, f"beet import failed:\nstdout: {result.stdout}\nstderr: {result.stderr}"

    cataloged = beets_svc.query_all_inbox_paths(inbox_config)
    assert cataloged, "DB is empty after catalog_path"
    assert str(standalone_flac) in cataloged, (
        f"Expected path not found.\n"
        f"  looking for: {str(standalone_flac)!r}\n"
        f"  DB contains: {cataloged}"
    )


def test_catalog_path_matching(inbox_config: Config, standalone_flac: Path) -> None:
    """str(path) matches what beets stores — the key invariant for cataloged detection."""
    beets_svc.catalog_path(inbox_config, standalone_flac, autotag=False)
    cataloged = beets_svc.query_all_inbox_paths(inbox_config)

    # This is the exact check _build_item does:
    assert str(standalone_flac) in cataloged, (
        "Path matching invariant broken.\n"
        "str(path) does not equal what beets stored.\n"
        f"  str(path):  {str(standalone_flac)!r}\n"
        f"  DB paths:   {cataloged}"
    )


def test_query_item_tags(inbox_config: Config, standalone_flac: Path) -> None:
    """Tags stored by beets match the Vorbis comments in the fixture."""
    beets_svc.catalog_path(inbox_config, standalone_flac, autotag=False)
    tags = beets_svc.query_item_tags(inbox_config, standalone_flac)

    assert tags.get("title") == "Standalone Track"
    assert tags.get("artist") == "Solo Artist"
    assert tags.get("album") == "Solo Single"
    assert tags.get("albumartist") == "Solo Artist"


def test_no_db_returns_empty(inbox_config: Config) -> None:
    """query_all_inbox_paths returns empty set when beets DB doesn't exist yet."""
    assert not inbox_config.beets_inbox_db.exists()
    assert beets_svc.query_all_inbox_paths(inbox_config) == set()


def test_autotag_false_passes_flag(inbox_config: Config, standalone_flac: Path) -> None:
    """-A flag is passed when autotag=False; import still succeeds."""
    result = beets_svc.catalog_path(inbox_config, standalone_flac, autotag=False)
    assert result.returncode == 0
    assert str(standalone_flac) in beets_svc.query_all_inbox_paths(inbox_config)
