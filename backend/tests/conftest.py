"""Shared pytest fixtures."""
from __future__ import annotations

import shutil
import sqlite3
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from music_importer.api import inbox as inbox_api
from music_importer.config import Config
from music_importer.services.beets import write_inbox_config, write_main_config

# Repo-level test fixtures directory
_FIXTURES_DIR = Path(__file__).parent.parent.parent / "test-fixtures"
_STANDALONE = _FIXTURES_DIR / "standalone.flac"
_ALBUM_DIR = _FIXTURES_DIR / "Inbox Album"


# ── Fixture file placement ────────────────────────────────────────────────────

def fixtures_dir() -> Path:
    return _FIXTURES_DIR


def place_standalone(config: Config, category: str = "unsorted") -> Path:
    """Copy the standalone FLAC fixture into a category dir of this inbox."""
    if not _STANDALONE.exists():
        pytest.skip("test-fixtures/standalone.flac missing — run: just make-fixtures")
    dest = config.inbox_path / category / _STANDALONE.name
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(_STANDALONE, dest)
    return dest


def place_album(config: Config, category: str = "unsorted") -> Path:
    """Copy the album-directory fixture into a category dir of this inbox."""
    if not _ALBUM_DIR.exists():
        pytest.skip("test-fixtures/Inbox Album missing — run: just make-fixtures")
    dest = config.inbox_path / category / _ALBUM_DIR.name
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(_ALBUM_DIR, dest)
    return dest


# ── Configs ───────────────────────────────────────────────────────────────────

@pytest.fixture()
def inbox_config(tmp_path: Path) -> Config:
    """A minimal Config pointing at a fresh temporary inbox (no main library)."""
    inbox = tmp_path / "inbox"
    data = tmp_path / "data"
    inbox.mkdir()
    data.mkdir()

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
def library_config(tmp_path: Path) -> Config:
    """A Config with both a temporary inbox and a temporary main library."""
    inbox = tmp_path / "inbox"
    data = tmp_path / "data"
    library = tmp_path / "library"
    inbox.mkdir()
    data.mkdir()
    library.mkdir()

    cfg = Config(
        inbox_path=inbox,
        data_path=data,
        default_category="unsorted",
        port=8085,
        library_path=library,
        autotag=False,
    )
    write_inbox_config(cfg)
    write_main_config(cfg, library)
    return cfg


@pytest.fixture()
def standalone_flac(inbox_config: Config) -> Path:
    """A standalone FLAC with known tags placed in the inbox."""
    return place_standalone(inbox_config)


@pytest.fixture()
def album_dir(inbox_config: Config) -> Path:
    """An album directory with known tags placed in the inbox."""
    return place_album(inbox_config)


# ── DB inspection helpers ─────────────────────────────────────────────────────

def main_db_items(config: Config) -> list[dict[str, Any]]:
    """Rows from the main library beets DB, decoded for assertions."""
    if not config.beets_main_db.exists():
        return []
    con = sqlite3.connect(str(config.beets_main_db))
    con.row_factory = sqlite3.Row
    try:
        rows = con.execute(
            "SELECT path, title, artist, album, albumartist, year, track FROM items"
        ).fetchall()
        result = []
        for row in rows:
            d = dict(row)
            if isinstance(d["path"], bytes):
                d["path"] = d["path"].decode()
            result.append(d)
        return result
    finally:
        con.close()


def library_files(config: Config) -> list[Path]:
    """All files physically present in the main library directory."""
    assert config.library_path is not None
    return sorted(p for p in config.library_path.rglob("*") if p.is_file())


# ── API test client ───────────────────────────────────────────────────────────

def make_client(config: Config) -> TestClient:
    """A TestClient serving the inbox API against the given config.

    Uses dependency_overrides instead of inbox_api.init() so no module-global
    state leaks between tests.  BackgroundTasks run synchronously inside the
    TestClient request cycle, so cataloging/import are complete when a
    request returns — no polling needed in tests.
    """
    app = FastAPI()
    app.include_router(inbox_api.router)
    app.dependency_overrides[inbox_api._cfg] = lambda: config  # noqa: SLF001
    return TestClient(app)


@pytest.fixture()
def client(library_config: Config) -> Iterator[TestClient]:
    """API client with a full inbox + main library setup."""
    with make_client(library_config) as c:
        yield c


@pytest.fixture()
def inbox_only_client(inbox_config: Config) -> Iterator[TestClient]:
    """API client with no main library configured."""
    with make_client(inbox_config) as c:
        yield c
