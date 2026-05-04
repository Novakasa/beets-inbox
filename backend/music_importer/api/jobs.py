"""Jobs API routes."""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from .. import db as db_mod
from ..config import Config
from ..models import Job

router = APIRouter(prefix="/api/jobs", tags=["jobs"])

_config: Config | None = None


def init(config: Config) -> None:
    global _config
    _config = config


def _cfg() -> Config:
    if _config is None:
        raise RuntimeError("jobs router not initialized")
    return _config


_ConfigDep = Annotated[Config, Depends(_cfg)]


@router.get("", response_model=list[Job])
def list_jobs(config: _ConfigDep, limit: int = 100) -> list[Job]:
    return db_mod.list_jobs(config.jobs_db, limit=limit)


@router.get("/{job_id}", response_model=Job)
def get_job(job_id: str, config: _ConfigDep) -> Job:
    job = db_mod.get_job(config.jobs_db, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return job
