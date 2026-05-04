# beets-inbox — task runner
# Run `just` to list available recipes.
# All recipes run from the repo root via `nix develop`.
# Backend code lives in backend/; run linters with `just check`.

set shell := ["bash", "-euo", "pipefail", "-c"]

_default:
    @just --list

# ── Backend ───────────────────────────────────────────────────────────────────

# Install/sync backend Python dependencies (including dev tools)
sync:
    cd backend && uv sync

# Run tests
test: sync
    cd backend && uv run pytest tests/ -v

# Run all linters (ruff + ty + basedpyright)
check: sync
    cd backend && uv run ruff check music_importer
    cd backend && uv run ty check music_importer
    cd backend && uv run basedpyright music_importer

# Auto-fix ruff issues
fmt: sync
    cd backend && uv run ruff check --fix music_importer
    cd backend && uv run ruff format music_importer

# Start the backend dev server (requires BEETS_INBOX_PATH to be set)
dev: sync
    cd backend && uv run uvicorn music_importer.main:app --reload --port 8085

# Start a demo server with a temporary inbox and library (no real beets library needed)
dev-demo: sync
    #!/usr/bin/env bash
    set -euo pipefail
    DEMO_DIR="$(mktemp -d /tmp/beets-inbox-demo.XXXXXX)"
    mkdir -p "$DEMO_DIR/inbox" "$DEMO_DIR/library" "$DEMO_DIR/data"
    echo "Demo dirs: $DEMO_DIR"
    echo "  inbox:   $DEMO_DIR/inbox"
    echo "  library: $DEMO_DIR/library"
    echo "  data:    $DEMO_DIR/data"
    echo "Open http://localhost:8085 in your browser"
    echo "Press Ctrl-C to stop and clean up"
    trap "rm -rf '$DEMO_DIR'; echo 'Cleaned up.'" EXIT
    export BEETS_INBOX_PATH="$DEMO_DIR/inbox"
    export BEETS_DATA_PATH="$DEMO_DIR/data"
    export BEETS_LIBRARY_PATH="$DEMO_DIR/library"
    cd backend && uv run uvicorn music_importer.main:app --reload --port 8085

# ── Test fixtures ─────────────────────────────────────────────────────────────

# Generate tiny tagged FLAC files in test-fixtures/ for manual testing
make-fixtures: sync
    cd backend && uv run python ../scripts/make_test_fixtures.py

# ── Validation ────────────────────────────────────────────────────────────────

# Validate the two-beets-libraries approach with real beets commands
validate-beets:
    bash scripts/validate-beets.sh

# ── Elm ───────────────────────────────────────────────────────────────────────

# Build the Elm frontend (optimised)
build-frontend:
    cd frontend && elm make src/Main.elm --optimize --output=dist/main.js

# Build the Elm frontend in debug mode (includes Elm debugger)
build-frontend-debug:
    cd frontend && elm make src/Main.elm --output=dist/main.js

# Type-check Elm without producing output
check-frontend:
    cd frontend && elm make src/Main.elm --output=/dev/null

# ── Misc ──────────────────────────────────────────────────────────────────────

# Show git status
status:
    git status
