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

# ── Validation ────────────────────────────────────────────────────────────────

# Validate the two-beets-libraries approach with real beets commands
validate-beets:
    bash scripts/validate-beets.sh

# ── Elm ───────────────────────────────────────────────────────────────────────

# Build the Elm frontend
build-frontend:
    cd frontend && elm make src/Main.elm --output=dist/main.js

# ── Misc ──────────────────────────────────────────────────────────────────────

# Show git status
status:
    git status
