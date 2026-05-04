"""FastAPI application entrypoint."""
from __future__ import annotations

import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from . import db as db_mod
from .api import inbox as inbox_api
from .api import jobs as jobs_api
from .config import load_config
from .services import beets as beets_svc
from .services.inbox import InboxWatcher

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Static files are built by Elm and placed here at build time (or served
# from a dev server during development).
# backend/music_importer/main.py → backend/ → repo root → frontend/dist
_STATIC_DIR = Path(__file__).parent.parent.parent / "frontend" / "dist"


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    config = load_config()

    # Ensure beets configs exist
    beets_svc.write_inbox_config(config)
    if config.library_path is not None:
        beets_svc.write_main_config(config, config.library_path)

    # Initialize job DB
    db_mod.init_db(config.jobs_db)

    # Wire API routers
    inbox_api.init(config)
    jobs_api.init(config)

    # Start inbox watcher
    watcher = InboxWatcher(config)
    watcher.start()

    logger.info("beets-inbox started on port %d", config.port)
    logger.info("  inbox:   %s", config.inbox_path)
    logger.info("  data:    %s", config.data_path)

    yield

    watcher.stop()


app = FastAPI(title="beets-inbox", lifespan=lifespan)

app.include_router(inbox_api.router)
app.include_router(jobs_api.router)

# Serve Elm frontend — only mount if the dist directory exists
if _STATIC_DIR.exists():
    app.mount("/", StaticFiles(directory=str(_STATIC_DIR), html=True), name="static")


def run() -> None:
    """Entry point for `uvicorn` (or direct invocation)."""
    import uvicorn

    config = load_config()
    uvicorn.run(
        "music_importer.main:app", host="0.0.0.0", port=config.port, reload=False
    )


if __name__ == "__main__":
    run()
