"""Shared pytest fixtures."""
from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from music_importer.config import Config

# Repo-level test fixtures directory
_FIXTURES_DIR = Path(__file__).parent.parent.parent / "test-fixtures"
_STANDALONE = _FIXTURES_DIR / "standalone.flac"
_ALBUM_DIR = _FIXTURES_DIR / "Inbox Album"


@pytest.fixture()
def inbox_config(tmp_path: Path) -> Config:
    """A minimal Config pointing at a fresh temporary inbox."""
    inbox = tmp_path / "inbox"
    data = tmp_path / "data"
    inbox.mkdir()
    data.mkdir()

    from music_importer.services.beets import write_inbox_config

    cfg = Config(
        inbox_path=inbox,
        data_path=data,
        default_category="unsorted",
        port=8085,
        library_path=None,
        autotag=False,
    )
    write_inbox_config(cfg)
    return cfg


@pytest.fixture()
def standalone_flac(inbox_config: Config) -> Path:
    """A standalone FLAC with known tags placed in the inbox."""
    if not _STANDALONE.exists():
        pytest.skip("test-fixtures/standalone.flac missing — run: just make-fixtures")
    dest = inbox_config.inbox_path / "unsorted" / _STANDALONE.name
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(_STANDALONE, dest)
    return dest


@pytest.fixture()
def album_dir(inbox_config: Config) -> Path:
    """An album directory with known tags placed in the inbox."""
    if not _ALBUM_DIR.exists():
        pytest.skip("test-fixtures/Inbox Album missing — run: just make-fixtures")
    dest = inbox_config.inbox_path / "unsorted" / _ALBUM_DIR.name
    shutil.copytree(_ALBUM_DIR, dest)
    return dest
