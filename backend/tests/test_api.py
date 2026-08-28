"""End-to-end tests at the HTTP layer — the same contract the Elm client uses.

Each test drives the FastAPI app through TestClient against real beets and
temporary inbox/library directories.  BackgroundTasks (cataloging, import)
run synchronously inside the TestClient request cycle, so responses are
deterministic — a completed upload request means cataloging is done.
"""
from __future__ import annotations

import io
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from music_importer.config import Config
from music_importer.services import beets as beets_svc

from .conftest import fixtures_dir, library_files, main_db_items, place_standalone

_ALBUM_DIR = fixtures_dir() / "Inbox Album"
_STANDALONE = fixtures_dir() / "standalone.flac"


def _standalone_bytes() -> bytes:
    if not _STANDALONE.exists():
        pytest.skip("test-fixtures/standalone.flac missing — run: just make-fixtures")
    return _STANDALONE.read_bytes()


def _album_zip(top_folder: str | None) -> bytes:
    """Build an in-memory ZIP of the album fixture.

    top_folder=None produces a flat ZIP; a name produces the Bandcamp-style
    single-top-level-folder layout.
    """
    if not _ALBUM_DIR.exists():
        pytest.skip("test-fixtures/Inbox Album missing — run: just make-fixtures")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for f in sorted(_ALBUM_DIR.glob("*.flac")):
            name = f"{top_folder}/{f.name}" if top_folder else f.name
            zf.writestr(name, f.read_bytes())
    return buf.getvalue()


def _upload_standalone(client: TestClient, **params: str) -> dict:
    resp = client.post(
        "/api/inbox/upload",
        params=params,
        files=[("files", ("standalone.flac", _standalone_bytes(), "audio/flac"))],
    )
    assert resp.status_code == 202, resp.text
    return resp.json()


def _only_item(client: TestClient) -> dict:
    items = client.get("/api/inbox").json()
    assert len(items) == 1, f"expected exactly 1 inbox item, got: {items}"
    return items[0]


# ── Upload ────────────────────────────────────────────────────────────────────

def test_upload_single_file_is_cataloged(client: TestClient) -> None:
    """Upload → catalog → the item shows up with tags from the beets DB."""
    body = _upload_standalone(client)
    assert len(body["placed"]) == 1

    item = _only_item(client)
    assert item["cataloged"] is True
    assert item["is_group"] is False
    assert item["category"] == "unsorted"
    assert item["title"] == "Standalone Track"
    assert item["artist"] == "Solo Artist"


def test_upload_to_named_category(client: TestClient) -> None:
    _upload_standalone(client, category="jazz")

    item = _only_item(client)
    assert item["category"] == "jazz"
    assert "jazz" in client.get("/api/inbox/categories").json()

    # Category filter returns the item; other categories are empty.
    assert len(client.get("/api/inbox", params={"category": "jazz"}).json()) == 1
    assert client.get("/api/inbox", params={"category": "rock"}).json() == []


def test_upload_zip_with_top_folder(client: TestClient) -> None:
    """Bandcamp-style ZIP (single top folder) becomes one cataloged group."""
    resp = client.post(
        "/api/inbox/upload",
        files=[("files", ("Inbox Album.zip", _album_zip("Inbox Album"), "application/zip"))],
    )
    assert resp.status_code == 202, resp.text

    item = _only_item(client)
    assert item["is_group"] is True
    assert item["cataloged"] is True
    assert len(item["files"]) == 3
    assert item["album"] == "Inbox Album"
    assert len(item["tracks"]) == 3
    assert {t["title"] for t in item["tracks"]} == {"Opening", "Interlude", "Closing"}


def test_upload_flat_zip_uses_zip_name(client: TestClient) -> None:
    """A flat ZIP is extracted into a folder named after the ZIP file."""
    resp = client.post(
        "/api/inbox/upload",
        files=[("files", ("My Flat Album.zip", _album_zip(None), "application/zip"))],
    )
    assert resp.status_code == 202, resp.text

    item = _only_item(client)
    assert item["is_group"] is True
    assert Path(item["path"]).name == "My Flat Album"
    assert len(item["files"]) == 3


# ── Tag update ────────────────────────────────────────────────────────────────

def test_patch_updates_tags(client: TestClient) -> None:
    _upload_standalone(client)
    item = _only_item(client)

    resp = client.patch(
        f"/api/inbox/{item['id']}",
        json={"artist": "Patched Artist", "album": "Patched Album"},
    )
    assert resp.status_code == 200, resp.text

    item = _only_item(client)
    assert item["artist"] == "Patched Artist"
    assert item["album"] == "Patched Album"
    assert item["title"] == "Standalone Track"  # untouched fields survive


def test_patch_uncataloged_item_conflicts(
    client: TestClient, library_config: Config
) -> None:
    """A file placed in the inbox but never cataloged can't be tag-edited."""
    place_standalone(library_config)

    item = _only_item(client)
    assert item["cataloged"] is False

    resp = client.patch(f"/api/inbox/{item['id']}", json={"artist": "X"})
    assert resp.status_code == 409


def test_patch_unknown_item_404(client: TestClient) -> None:
    assert client.patch("/api/inbox/deadbeef", json={"artist": "X"}).status_code == 404


# ── Import ────────────────────────────────────────────────────────────────────

def test_import_moves_item_to_library(
    client: TestClient, library_config: Config
) -> None:
    """The full accept flow: upload → import → library has it, inbox is clean."""
    _upload_standalone(client)
    item = _only_item(client)
    src = Path(item["path"])

    resp = client.post(f"/api/inbox/{item['id']}/import")
    assert resp.status_code == 202, resp.text

    # Import ran synchronously (TestClient): file landed in the library …
    files = library_files(library_config)
    assert len(files) == 1, f"expected 1 library file, got: {files}"
    items = main_db_items(library_config)
    assert len(items) == 1
    assert items[0]["title"] == "Standalone Track"

    # … and the inbox is fully cleaned up: source file, listing, and DB entry.
    assert not src.exists()
    assert client.get("/api/inbox").json() == []
    assert beets_svc.query_all_inbox_paths(library_config) == set()


def test_import_uses_patched_tags(client: TestClient, library_config: Config) -> None:
    """Tags edited via PATCH are what ends up in the main library."""
    _upload_standalone(client)
    item = _only_item(client)

    resp = client.patch(f"/api/inbox/{item['id']}", json={"artist": "Final Artist"})
    assert resp.status_code == 200

    resp = client.post(f"/api/inbox/{item['id']}/import")
    assert resp.status_code == 202

    items = main_db_items(library_config)
    assert len(items) == 1
    assert items[0]["artist"] == "Final Artist"


def test_import_album_keeps_per_track_tags(
    client: TestClient, library_config: Config
) -> None:
    """Importing an album group must not clobber per-track title/track number."""
    resp = client.post(
        "/api/inbox/upload",
        files=[("files", ("Inbox Album.zip", _album_zip("Inbox Album"), "application/zip"))],
    )
    assert resp.status_code == 202, resp.text
    item = _only_item(client)

    resp = client.post(f"/api/inbox/{item['id']}/import")
    assert resp.status_code == 202, resp.text

    items = main_db_items(library_config)
    assert len(items) == 3
    assert {i["title"] for i in items} == {"Opening", "Interlude", "Closing"}
    assert {i["track"] for i in items} == {1, 2, 3}
    assert all(i["album"] == "Inbox Album" for i in items)

    # Inbox fully cleaned up.
    assert not Path(item["path"]).exists()
    assert client.get("/api/inbox").json() == []


def test_import_without_library_is_503(inbox_only_client: TestClient) -> None:
    _upload_standalone(inbox_only_client)
    item = _only_item(inbox_only_client)

    resp = inbox_only_client.post(f"/api/inbox/{item['id']}/import")
    assert resp.status_code == 503


def test_import_unknown_item_404(client: TestClient) -> None:
    assert client.post("/api/inbox/deadbeef/import").status_code == 404


# ── Discard ───────────────────────────────────────────────────────────────────

def test_discard_removes_file_and_db_entry(
    client: TestClient, library_config: Config
) -> None:
    _upload_standalone(client)
    item = _only_item(client)
    src = Path(item["path"])

    resp = client.delete(f"/api/inbox/{item['id']}")
    assert resp.status_code == 204

    assert not src.exists()
    assert client.get("/api/inbox").json() == []
    assert beets_svc.query_all_inbox_paths(library_config) == set()
    # Nothing leaked into the main library.
    assert library_files(library_config) == []


def test_discard_unknown_item_404(client: TestClient) -> None:
    assert client.delete("/api/inbox/deadbeef").status_code == 404
