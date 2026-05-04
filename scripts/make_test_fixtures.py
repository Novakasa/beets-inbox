#!/usr/bin/env python3
"""Generate tiny tagged FLAC test fixtures for beets-inbox.

Requires sox (from the nix dev shell) and mutagen (Python dev dep).

Run from the repo root:
    just make-fixtures
"""
from __future__ import annotations

import subprocess
from pathlib import Path

from mutagen.flac import FLAC

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURES_DIR = REPO_ROOT / "test-fixtures"

_ALBUM = dict(
    artist="Inbox Artist",
    album="Inbox Album",
    albumartist="Inbox Artist",
    genre="Electronic",
    date="2024",
)

FIXTURES: list[tuple[str, dict[str, str]]] = [
    ("Inbox Album/01 - Opening.flac",   {**_ALBUM, "title": "Opening",   "tracknumber": "1"}),
    ("Inbox Album/02 - Interlude.flac", {**_ALBUM, "title": "Interlude", "tracknumber": "2"}),
    ("Inbox Album/03 - Closing.flac",   {**_ALBUM, "title": "Closing",   "tracknumber": "3"}),
    (
        "standalone.flac",
        {
            "title": "Standalone Track",
            "artist": "Solo Artist",
            "album": "Solo Single",
            "albumartist": "Solo Artist",
            "genre": "Ambient",
            "date": "2023",
            "tracknumber": "1",
        },
    ),
]


def make_silent_flac(path: Path, tags: dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    # 0.1 s of silence, mono, 16-bit, 44100 Hz
    subprocess.run(
        ["sox", "-n", "-r", "44100", "-c", "1", "-b", "16", str(path), "trim", "0", "0.1"],
        check=True,
    )
    f = FLAC(str(path))
    for key, val in tags.items():
        f[key] = [val]
    f.save()


def main() -> None:
    for rel_path, tags in FIXTURES:
        dest = FIXTURES_DIR / rel_path
        make_silent_flac(dest, tags)
        print(f"  {dest.relative_to(REPO_ROOT)}")
    print(f"\nDone — {len(FIXTURES)} fixtures in test-fixtures/")


if __name__ == "__main__":
    main()
