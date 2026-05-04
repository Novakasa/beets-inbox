"""Tests for inbox scanning, item building, and cataloged-state detection."""
from __future__ import annotations

from pathlib import Path

from music_importer.config import Config
from music_importer.services import beets as beets_svc
from music_importer.services import inbox as inbox_svc


def test_scan_returns_uncataloged_item(inbox_config: Config, standalone_flac: Path) -> None:
    """A freshly uploaded file shows up as not cataloged before beets runs."""
    items = inbox_svc.scan_inbox(inbox_config)
    assert len(items) == 1
    item = items[0]
    assert item.cataloged is False
    assert item.title is None


def test_scan_returns_cataloged_item(inbox_config: Config, standalone_flac: Path) -> None:
    """After catalog_path, the item is marked cataloged and has tags."""
    beets_svc.catalog_path(inbox_config, standalone_flac, autotag=False)

    items = inbox_svc.scan_inbox(inbox_config)
    assert len(items) == 1
    item = items[0]
    assert item.cataloged is True
    assert item.title == "Standalone Track"
    assert item.artist == "Solo Artist"


def test_scan_album_group(inbox_config: Config, album_dir: Path) -> None:
    """An album directory is returned as a single group item."""
    items = inbox_svc.scan_inbox(inbox_config)
    assert len(items) == 1
    item = items[0]
    assert item.is_group is True
    assert len(item.files) == 3


def test_scan_album_cataloged(inbox_config: Config, album_dir: Path) -> None:
    """After cataloging, all album tracks are detected and tags surface."""
    beets_svc.catalog_path(inbox_config, album_dir, autotag=False)

    items = inbox_svc.scan_inbox(inbox_config)
    assert len(items) == 1
    item = items[0]
    assert item.cataloged is True
    assert item.artist == "Inbox Artist"
    assert item.album == "Inbox Album"


def test_list_categories(inbox_config: Config, standalone_flac: Path) -> None:
    categories = inbox_svc.list_categories(inbox_config)
    assert "unsorted" in categories


def test_get_item_roundtrip(inbox_config: Config, standalone_flac: Path) -> None:
    """path_to_id → get_item roundtrips correctly."""
    item_id = inbox_svc.path_to_id(inbox_config.inbox_path, standalone_flac)
    item = inbox_svc.get_item(inbox_config, item_id)
    assert item is not None
    assert item.id == item_id
    assert item.path == str(standalone_flac)
