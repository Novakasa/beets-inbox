#!/usr/bin/env python3
"""Generate tiny tagged FLAC test fixtures for beets-inbox.

Creates two album tracks and one standalone single in test-fixtures/.
Files are minimal silent FLACs (~500 B each) built without ffmpeg.

Run from the repo root inside the dev shell:
    cd backend && uv run python ../scripts/make_test_fixtures.py
"""
from __future__ import annotations

import hashlib
import struct
from pathlib import Path


# ── Minimal FLAC binary builder ───────────────────────────────────────────────
#
# FLAC format (simplified):
#   fLaC magic (4 bytes)
#   STREAMINFO metadata block
#   VORBIS_COMMENT metadata block  ← mutagen overwrites this when we tag
#   One CONSTANT audio frame (256 silent samples)


def _crc8(data: bytes) -> int:
    """CRC-8 with polynomial 0x07, used in FLAC frame headers."""
    crc = 0
    for byte in data:
        crc ^= byte
        for _ in range(8):
            crc = ((crc << 1) ^ 0x07 if crc & 0x80 else crc << 1) & 0xFF
    return crc


def _crc16(data: bytes) -> int:
    """CRC-16 with polynomial 0x8005, used in FLAC frame footers."""
    crc = 0
    for byte in data:
        crc ^= byte << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x8005 if crc & 0x8000 else crc << 1) & 0xFFFF
    return crc


def _metadata_block(block_type: int, data: bytes, *, last: bool) -> bytes:
    hdr = ((0x80 if last else 0x00) | block_type).to_bytes(1)
    return hdr + len(data).to_bytes(3, "big") + data


def _vorbis_comment_block(tags: dict[str, str]) -> bytes:
    """Build a raw FLAC VORBIS_COMMENT (type 4) payload.

    Format: vendor_length(4LE) vendor_string comments_count(4LE)
            [comment_length(4LE) "KEY=VALUE"] ...
    """
    vendor = b"beets-inbox-fixtures"
    comments = [f"{k.upper()}={v}".encode() for k, v in tags.items()]
    payload = struct.pack("<I", len(vendor)) + vendor
    payload += struct.pack("<I", len(comments))
    for c in comments:
        payload += struct.pack("<I", len(c)) + c
    return payload


def _streaminfo(
    sample_rate: int = 44100,
    channels: int = 1,
    bps: int = 16,
    block_size: int = 256,
    total_samples: int = 256,
) -> bytes:
    """34-byte STREAMINFO payload."""
    data = bytearray(34)
    struct.pack_into(">HH", data, 0, block_size, block_size)
    # min/max frame size = 0 (unknown) — bytes 4-9 already zero
    # Packed: sample_rate(20) | channels-1(3) | bps-1(5) | total_samples(36)
    packed = (
        ((sample_rate & 0xFFFFF) << 44)
        | ((channels - 1) << 41)
        | ((bps - 1) << 36)
        | (total_samples & 0xFFFFFFFFFF)
    )
    struct.pack_into(">Q", data, 10, packed)
    # MD5 of 256 * 2 = 512 zero bytes (bytes 18-33)
    md5 = hashlib.md5(bytes(total_samples * (bps // 8))).digest()
    data[18:34] = md5
    return bytes(data)


def _audio_frame(block_size: int = 256, bps: int = 16) -> bytes:
    """One CONSTANT subframe frame (all samples = 0).

    Frame header layout (fixed-blocksize, mono, 16-bit, 44.1 kHz):
      sync(14) reserved(1) blocking_strategy(1)  →  0xFF 0xF8
      block_size_code(4) sample_rate_code(4)      →  0x88  (1000=256 samples, 1000=44.1kHz)
      channel_assignment(4) sample_size(3) rsv(1) →  0x08  (mono, 16-bit)
      frame_number UTF-8-encoded (frame 0)        →  0x00
      CRC-8
    """
    header_pre_crc = bytes([0xFF, 0xF8, 0x88, 0x08, 0x00])
    frame_header = header_pre_crc + bytes([_crc8(header_pre_crc)])

    # CONSTANT subframe: header byte (0x00) + one bps-bit sample value (0)
    subframe = bytes([0x00]) + (0).to_bytes(bps // 8, "big")

    frame_body = frame_header + subframe
    return frame_body + struct.pack(">H", _crc16(frame_body))


def build_flac(tags: dict[str, str]) -> bytes:
    """Assemble a minimal valid FLAC file (256 silent samples) with tags."""
    return (
        b"fLaC"
        + _metadata_block(0, _streaminfo(), last=False)  # STREAMINFO
        + _metadata_block(4, _vorbis_comment_block(tags), last=True)  # VORBIS_COMMENT
        + _audio_frame()
    )


# ── Fixture definitions ───────────────────────────────────────────────────────

_ALBUM = dict(
    artist="Inbox Artist",
    album="Inbox Album",
    albumartist="Inbox Artist",
    genre="Electronic",
    date="2024",
)

FIXTURES: list[tuple[str, dict[str, str]]] = [
    (
        "Inbox Album/01 - Opening.flac",
        {**_ALBUM, "title": "Opening", "tracknumber": "1"},
    ),
    (
        "Inbox Album/02 - Interlude.flac",
        {**_ALBUM, "title": "Interlude", "tracknumber": "2"},
    ),
    (
        "Inbox Album/03 - Closing.flac",
        {**_ALBUM, "title": "Closing", "tracknumber": "3"},
    ),
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


def main() -> None:
    repo_root = Path(__file__).resolve().parent.parent
    fixtures_dir = repo_root / "test-fixtures"

    for rel_path, tags in FIXTURES:
        dest = fixtures_dir / rel_path
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(build_flac(tags))
        print(f"  {dest.relative_to(repo_root)}")

    print(f"\nDone — {len(FIXTURES)} fixtures in test-fixtures/")


if __name__ == "__main__":
    main()
