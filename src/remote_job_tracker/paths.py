"""Shared project and persistent-data paths."""

from __future__ import annotations

import os
from pathlib import Path

PROJECT_ROOT = Path(
    os.environ.get("JOB_TRACKER_PROJECT_DIR", Path(__file__).resolve().parents[2])
)


def data_directory() -> Path:
    configured = os.environ.get("JOB_TRACKER_DATA_DIR")
    return Path(configured).expanduser() if configured else PROJECT_ROOT
