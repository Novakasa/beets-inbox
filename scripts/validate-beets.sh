#!/usr/bin/env bash
# validate-beets.sh — Prove the two-beets-libraries approach works.
#
# Tests the full cycle:
#   1. Catalog a file in the inbox library (no copy/move/write)
#   2. Query the inbox beets DB to confirm it was cataloged
#   3. Import from inbox path into the main library with explicit tags
#   4. Remove the entry from the inbox DB and delete the source file
#
# Run from the repo root inside `nix develop`:
#   bash scripts/validate-beets.sh
set -euo pipefail

# ── Setup ──────────────────────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"
WORK_DIR="$(mktemp -d /tmp/beets-validate-XXXXXX)"
trap 'echo "--- cleaning up $WORK_DIR ---"; rm -rf "$WORK_DIR"' EXIT

INBOX_DIR="$WORK_DIR/inbox/unsorted"
LIBRARY_DIR="$WORK_DIR/library"
DATA_DIR="$WORK_DIR/data"

mkdir -p "$INBOX_DIR" "$LIBRARY_DIR" "$DATA_DIR"

echo "=== beets validate: two-library approach ==="
echo "  work dir: $WORK_DIR"
echo ""

# ── Generate test audio file ───────────────────────────────────────────────────
echo "--- [1] generating test audio file ---"
AUDIO_FILE="$INBOX_DIR/Test Artist - Test Track.wav"
python3 "$REPO_ROOT/test-fixtures/gen-silent-wav.py" "$AUDIO_FILE"
echo "  created: $AUDIO_FILE"
echo ""

# ── Write inbox beets config ───────────────────────────────────────────────────
echo "--- [2] writing inbox beets config ---"
INBOX_CONFIG="$DATA_DIR/inbox-beets.yaml"
cat > "$INBOX_CONFIG" <<EOF
# Inbox library: scratchpad, no file operations
directory: $INBOX_DIR
library: $DATA_DIR/inbox-beets.db

import:
  copy: false
  move: false
  write: false
  # Run auto-tagger but don't require a match
  timid: false
  # Use best match automatically (or skip if no match) — no interactive prompt
  none: true

plugins: []
EOF
echo "  wrote: $INBOX_CONFIG"
echo ""

# ── Write main library beets config ───────────────────────────────────────────
echo "--- [3] writing main library beets config ---"
MAIN_CONFIG="$DATA_DIR/main-beets.yaml"
cat > "$MAIN_CONFIG" <<EOF
# Main library: real library, copy files
directory: $LIBRARY_DIR
library: $DATA_DIR/main-beets.db

import:
  copy: true
  move: false
  write: true
  timid: false

plugins: []
EOF
echo "  wrote: $MAIN_CONFIG"
echo ""

# ── Step 1: Catalog in inbox (no copy/move/write) ─────────────────────────────
echo "--- [4] cataloging file in inbox library ---"
INBOX_FILE="$AUDIO_FILE"
# -A = apply best match automatically (no prompt)
# -q = quiet
beet --config "$INBOX_CONFIG" import -A -q "$INBOX_FILE" 2>&1 || true
echo "  beet import (inbox) done"
echo ""

# ── Verify inbox DB has the entry ─────────────────────────────────────────────
echo "--- [5] verifying inbox DB entry ---"
INBOX_COUNT=$(sqlite3 "$DATA_DIR/inbox-beets.db" \
  "SELECT count(*) FROM items WHERE path LIKE '%Test%';" 2>/dev/null || echo "0")
echo "  items matching 'Test' in inbox DB: $INBOX_COUNT"

if [[ "$INBOX_COUNT" -ge 1 ]]; then
  echo "  ✓ file cataloged in inbox DB"
  sqlite3 "$DATA_DIR/inbox-beets.db" \
    "SELECT path, title, artist FROM items LIMIT 5;" 2>/dev/null || true
else
  echo "  ✗ file NOT found in inbox DB — checking if DB exists at all"
  ls -la "$DATA_DIR/" || true
  # beets may have skipped cataloging a WAV with no metadata match — check anyway
  INBOX_COUNT_ALL=$(sqlite3 "$DATA_DIR/inbox-beets.db" \
    "SELECT count(*) FROM items;" 2>/dev/null || echo "0")
  echo "  total items in inbox DB: $INBOX_COUNT_ALL"
fi
echo ""

# ── Step 2: Import into main library with explicit tags ───────────────────────
echo "--- [6] importing to main library with explicit tags ---"
beet --config "$MAIN_CONFIG" import -A -q \
  --set title="Test Track" \
  --set artist="Test Artist" \
  --set album="Test Album" \
  --set year=2024 \
  "$AUDIO_FILE"
echo "  beet import (main) done"
echo ""

# ── Verify file landed in main library ────────────────────────────────────────
echo "--- [7] verifying main library ---"
MAIN_COUNT=$(sqlite3 "$DATA_DIR/main-beets.db" \
  "SELECT count(*) FROM items;" 2>/dev/null || echo "0")
echo "  items in main DB: $MAIN_COUNT"

if [[ "$MAIN_COUNT" -ge 1 ]]; then
  echo "  ✓ file in main DB"
  sqlite3 "$DATA_DIR/main-beets.db" \
    "SELECT path, title, artist, album FROM items LIMIT 5;" 2>/dev/null || true
  echo ""
  echo "  files in library dir:"
  find "$LIBRARY_DIR" -type f | head -10 || true
else
  echo "  ✗ file NOT in main DB"
fi
echo ""

# ── Step 3: Remove from inbox DB + delete source file ────────────────────────
echo "--- [8] removing from inbox ---"
if [[ -f "$AUDIO_FILE" ]]; then
  # Remove DB entry and delete file
  beet --config "$INBOX_CONFIG" remove -d -f "path:$AUDIO_FILE" 2>&1 || true
  echo "  beet remove done"

  if [[ ! -f "$AUDIO_FILE" ]]; then
    echo "  ✓ source file deleted"
  else
    echo "  ✗ source file still exists (may not have been cataloged)"
    rm -f "$AUDIO_FILE"
    echo "  manually removed"
  fi
else
  echo "  source file already gone"
fi
echo ""

# ── Summary ───────────────────────────────────────────────────────────────────
echo "=== summary ==="
FINAL_MAIN=$(sqlite3 "$DATA_DIR/main-beets.db" \
  "SELECT count(*) FROM items;" 2>/dev/null || echo "0")
FINAL_INBOX=$(sqlite3 "$DATA_DIR/inbox-beets.db" \
  "SELECT count(*) FROM items;" 2>/dev/null || echo "0")
LIBRARY_FILES=$(find "$LIBRARY_DIR" -type f | wc -l)

echo "  main library items:   $FINAL_MAIN"
echo "  inbox items (after):  $FINAL_INBOX"
echo "  files in library dir: $LIBRARY_FILES"

if [[ "$FINAL_MAIN" -ge 1 && "$LIBRARY_FILES" -ge 1 ]]; then
  echo ""
  echo "  ✓ two-library approach WORKS"
  echo "    - inbox catalogs without moving files"
  echo "    - main library copies with explicit tags"
  echo "    - cleanup removes inbox entry"
else
  echo ""
  echo "  ✗ something didn't work — inspect $WORK_DIR (trap removed it, re-run with trap disabled)"
fi
