from __future__ import annotations

from pathlib import Path

from ...modules.execution.store import ExecutionStore


class SqliteExecutionQueue(ExecutionStore):
    """SQLite implementation of the execution queue port."""

    def __init__(self, path: Path, lease_seconds: int = 45, worker_stale_seconds: int = 15):
        super().__init__(path, lease_seconds=lease_seconds, worker_stale_seconds=worker_stale_seconds)
