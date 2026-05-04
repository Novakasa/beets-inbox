"""Application configuration loaded from environment variables."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Config:
    inbox_path: Path
    data_path: Path
    default_category: str
    port: int
    library_path: Path | None  # None = no generated main config (user supplies one)

    @property
    def beets_inbox_config(self) -> Path:
        return self.data_path / "inbox-beets.yaml"

    @property
    def beets_inbox_db(self) -> Path:
        return self.data_path / "inbox-beets.db"

    @property
    def beets_main_config(self) -> Path:
        return self.data_path / "main-beets.yaml"

    @property
    def beets_main_db(self) -> Path:
        return self.data_path / "main-beets.db"

    @property
    def jobs_db(self) -> Path:
        return self.data_path / "jobs.db"


def load_config() -> Config:
    inbox_path = Path(os.environ["BEETS_INBOX_PATH"])
    data_path = Path(os.environ.get("BEETS_DATA_PATH", str(inbox_path / ".data")))
    default_category = os.environ.get("BEETS_DEFAULT_CATEGORY", "unsorted")
    port = int(os.environ.get("BEETS_INBOX_PORT", "8085"))
    library_path = Path(lp) if (lp := os.environ.get("BEETS_LIBRARY_PATH")) else None

    data_path.mkdir(parents=True, exist_ok=True)

    return Config(
        inbox_path=inbox_path,
        data_path=data_path,
        default_category=default_category,
        port=port,
        library_path=library_path,
    )
