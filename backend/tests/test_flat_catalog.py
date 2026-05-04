"""Reproduce the production scenario: multiple individual files in a flat
category directory, each cataloged via a separate catalog_path call."""
from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from music_importer.config import Config
from music_importer.services import beets as beets_svc
from music_importer.services import inbox as inbox_svc

_ALBUM_DIR = Path(__file__).parent.parent.parent / "test-fixtures" / "Inbox Album"


@pytest.fixture()
def flat_files(inbox_config: Config) -> list[Path]:
    """Three FLAC files placed directly in unsorted/ (not in a subdirectory)."""
    if not _ALBUM_DIR.exists():
        pytest.skip("test-fixtures/Inbox Album missing — run: just make-fixtures")
    dest_dir = inbox_config.inbox_path / "unsorted"
    dest_dir.mkdir(parents=True, exist_ok=True)
    placed = []
    for src in sorted(_ALBUM_DIR.glob("*.flac")):
        dst = dest_dir / src.name
        shutil.copy(src, dst)
        placed.append(dst)
    return placed


def test_flat_files_are_separate_items(inbox_config: Config, flat_files: list[Path]) -> None:
    """Three flat files should appear as three separate inbox items."""
    items = inbox_svc.scan_inbox(inbox_config)
    assert len(items) == 3
    assert all(not i.is_group for i in items)


def test_catalog_each_flat_file_individually(inbox_config: Config, flat_files: list[Path]) -> None:
    """Catalog each file with a separate beet call (as the upload endpoint does)."""
    for f in flat_files:
        result = beets_svc.catalog_path(inbox_config, f, autotag=False)
        assert result.returncode == 0, (
            f"beet import failed for {f.name}:\n"
            f"  stdout: {result.stdout}\n"
            f"  stderr: {result.stderr}"
        )

    cataloged = beets_svc.query_all_inbox_paths(inbox_config)
    print(f"\nDB contains {len(cataloged)} path(s):")
    for p in sorted(cataloged):
        print(f"  {p}")

    for f in flat_files:
        assert str(f) in cataloged, (
            f"Not in DB after individual catalog:\n"
            f"  file:   {str(f)!r}\n"
            f"  DB:     {sorted(cataloged)}"
        )


def test_scan_all_flat_files_cataloged(inbox_config: Config, flat_files: list[Path]) -> None:
    """After cataloging each file, scan_inbox should mark all as cataloged."""
    for f in flat_files:
        beets_svc.catalog_path(inbox_config, f, autotag=False)

    items = inbox_svc.scan_inbox(inbox_config)
    not_cataloged = [i for i in items if not i.cataloged]
    assert not not_cataloged, (
        f"{len(not_cataloged)} item(s) not cataloged:\n"
        + "\n".join(f"  {i.path}" for i in not_cataloged)
    )
