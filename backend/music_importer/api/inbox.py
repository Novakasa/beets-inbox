"""Inbox API routes."""
from __future__ import annotations

import io
import logging
import shutil
import threading
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, UploadFile
from fastapi.responses import JSONResponse

from .. import db as db_mod
from ..config import Config
from ..models import ImportRequest, InboxItem, Job, JobStatus
from ..services import beets as beets_svc
from ..services import inbox as inbox_svc

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/inbox", tags=["inbox"])

# Injected by main.py at startup
_config: Config | None = None
_import_lock = threading.Lock()


def init(config: Config) -> None:
    global _config
    _config = config


def _cfg() -> Config:
    if _config is None:
        raise RuntimeError("inbox router not initialized")
    return _config


_ConfigDep = Annotated[Config, Depends(_cfg)]


# ── List ──────────────────────────────────────────────────────────────────────

@router.get("", response_model=list[InboxItem])
def list_inbox(
    config: _ConfigDep,
    category: str | None = None,
) -> list[InboxItem]:
    items = inbox_svc.scan_inbox(config)
    if category:
        items = [i for i in items if i.category == category]
    return items


@router.get("/categories", response_model=list[str])
def list_categories(config: _ConfigDep) -> list[str]:
    return inbox_svc.list_categories(config)


# ── Upload ────────────────────────────────────────────────────────────────────

@router.post("/upload", status_code=202)
async def upload(
    files: list[UploadFile],
    background_tasks: BackgroundTasks,
    config: _ConfigDep,
    category: str | None = None,
) -> JSONResponse:
    cat = category or config.default_category
    dest_dir = config.inbox_path / cat
    dest_dir.mkdir(parents=True, exist_ok=True)

    placed: list[str] = []
    for upload_file in files:
        filename = upload_file.filename or "upload"
        data = await upload_file.read()

        if filename.lower().endswith(".zip"):
            placed += _extract_zip(data, dest_dir)
        else:
            dest = dest_dir / filename
            dest.write_bytes(data)
            placed.append(str(dest))

    # Catalog immediately after upload (don't wait for watcher)
    for p in placed:
        path = Path(p)
        if inbox_svc.is_audio(path) or path.is_dir():
            background_tasks.add_task(beets_svc.catalog_path, config, path)

    return JSONResponse({"placed": placed})


def _extract_zip(data: bytes, dest_dir: Path) -> list[str]:
    """Extract ZIP, collapsing a single top-level directory into an album group."""
    placed: list[str] = []
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        names = zf.namelist()
        # Detect single top-level directory (bandcamp ZIP pattern)
        top_dirs = {n.split("/")[0] for n in names if "/" in n}
        top = next(iter(top_dirs)) if top_dirs else None
        single_top = (
            top is not None
            and len(top_dirs) == 1
            and all(n.startswith(top) for n in names)
        )

        if single_top and top is not None:
            album_dir = dest_dir / top
            album_dir.mkdir(exist_ok=True)
            for member in zf.infolist():
                rel = member.filename[len(top) + 1:]
                if not rel or member.is_dir():
                    continue
                out = album_dir / rel
                out.parent.mkdir(parents=True, exist_ok=True)
                out.write_bytes(zf.read(member.filename))
                placed.append(str(out))
        else:
            for member in zf.infolist():
                if member.is_dir():
                    continue
                out = dest_dir / Path(member.filename).name
                out.write_bytes(zf.read(member.filename))
                placed.append(str(out))

    return placed


# ── Import ────────────────────────────────────────────────────────────────────

@router.post("/{item_id}/import", response_model=Job)
def import_item(
    item_id: str,
    req: ImportRequest,
    background_tasks: BackgroundTasks,
    config: _ConfigDep,
) -> Job:
    item = inbox_svc.get_item(config, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Inbox item not found")

    job = db_mod.create_job(
        config.jobs_db,
        source_path=item.path,
        category=item.category,
        artist=req.artist,
        album=req.album,
        genre=req.genre,
    )
    background_tasks.add_task(_run_import, config, item, req, job.id)
    return job


def _run_import(
    config: Config, item: InboxItem, req: ImportRequest, job_id: str
) -> None:
    db_mod.update_job(config.jobs_db, job_id, JobStatus.running)
    log_lines: list[str] = []

    try:
        tags = req.model_dump(exclude_none=True)
        path = Path(item.path)

        # 1. Import to main library
        log_lines.append(f"Importing {path} with tags {tags}\n")
        result = beets_svc.import_to_library(config, path, tags)
        log_lines.append(result.stdout)
        if result.returncode != 0:
            log_lines.append(f"stderr: {result.stderr}\n")
            raise RuntimeError(f"beet import failed (rc={result.returncode})")

        # 2. Remove from inbox DB + delete source file
        log_lines.append("Removing from inbox...\n")
        rm_result = beets_svc.remove_from_inbox(config, path)
        log_lines.append(rm_result.stdout)
        if rm_result.returncode != 0:
            logger.warning(
                "beet remove returned %d: %s",
                rm_result.returncode,
                rm_result.stderr,
            )

        # 3. Clean up sidecar files
        if not item.is_group:
            _clean_sidecars(path)

        db_mod.update_job(
            config.jobs_db, job_id, JobStatus.success,
            log="".join(log_lines),
            completed_at=datetime.now(UTC),
        )
    except Exception as exc:
        logger.exception("Import job %s failed", job_id)
        db_mod.update_job(
            config.jobs_db, job_id, JobStatus.failed,
            log="".join(log_lines) + f"\nError: {exc}",
            completed_at=datetime.now(UTC),
        )


def _clean_sidecars(audio_path: Path) -> None:
    """Delete .info.json sidecar(s) alongside an audio file."""
    sidecar = audio_path.with_suffix(audio_path.suffix + ".info.json")
    if sidecar.exists():
        sidecar.unlink()
        logger.debug("Deleted sidecar %s", sidecar)


# ── Discard ───────────────────────────────────────────────────────────────────

@router.delete("/{item_id}", status_code=204)
def discard_item(item_id: str, config: _ConfigDep) -> None:
    item = inbox_svc.get_item(config, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Inbox item not found")

    path = Path(item.path)

    # Remove from inbox beets DB
    beets_svc.remove_from_inbox(config, path)

    # Delete the file(s)
    if path.is_dir():
        shutil.rmtree(path, ignore_errors=True)
    elif path.is_file():
        path.unlink(missing_ok=True)
        _clean_sidecars(path)
