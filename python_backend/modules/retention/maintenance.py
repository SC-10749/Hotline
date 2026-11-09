from __future__ import annotations

import sqlite3
import threading
import time
from pathlib import Path
from typing import Any, Callable


def _cutoff(days: int) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() - max(1, int(days)) * 86400))


def _connect(path: Path) -> sqlite3.Connection:
    db = sqlite3.connect(path, timeout=30)
    try:
        return db
    except Exception:
        db.close()
        raise


def purge_execution_history(path: Path, retention_days: int) -> dict[str, int]:
    """Delete finished runs and their events older than the audit retention window."""
    cutoff = _cutoff(retention_days)
    if not Path(path).is_file():
        return {'runs': 0, 'events': 0}
    db = _connect(Path(path))
    try:
        with db:
            events = db.execute(
                "DELETE FROM execution_event WHERE created_at < ?", (cutoff,)
            ).rowcount
            runs = db.execute(
                """DELETE FROM execution_run WHERE status IN ('completed','failed','cancelled')
                   AND created_at < ?""", (cutoff,)
            ).rowcount
        return {'runs': max(0, runs), 'events': max(0, events)}
    finally:
        db.close()


def purge_approvals(path: Path, retention_days: int) -> int:
    """Delete decided approval records older than the audit retention window."""
    cutoff = _cutoff(retention_days)
    if not Path(path).is_file():
        return 0
    db = _connect(Path(path))
    try:
        with db:
            removed = db.execute(
                "DELETE FROM harness_approval WHERE status != 'pending' AND created_at < ?", (cutoff,)
            ).rowcount
        return max(0, removed)
    finally:
        db.close()


def purge_artifacts(path: Path, retention_days: int) -> int:
    """Delete artifact registrations older than the artifact retention window."""
    cutoff = _cutoff(retention_days)
    if not Path(path).is_file():
        return 0
    db = _connect(Path(path))
    try:
        with db:
            removed = db.execute(
                "DELETE FROM run_artifact WHERE created_at < ?", (cutoff,)
            ).rowcount
        return max(0, removed)
    finally:
        db.close()


def run_retention(paths: dict[str, Path], settings: dict[str, Any]) -> dict[str, int]:
    """Apply the configured retention windows to every audit trail this project keeps."""
    audit_days = int(settings.get('auditRetentionDays') or 30)
    artifact_days = int(settings.get('artifactRetentionDays') or audit_days)
    result: dict[str, int] = {}
    if 'execution' in paths:
        result.update(purge_execution_history(paths['execution'], audit_days))
    if 'governance' in paths:
        result['approvals'] = purge_approvals(paths['governance'], audit_days)
    if 'artifacts' in paths:
        result['artifacts'] = purge_artifacts(paths['artifacts'], artifact_days)
    return result


def start_retention_loop(paths: dict[str, Path], settings_provider: Callable[[], dict[str, Any]],
                         interval: int = 3600) -> threading.Event:
    """Run retention cleanup on a fixed interval so the stored window is honoured."""
    stop = threading.Event()

    def loop() -> None:
        while not stop.wait(interval):
            try:
                run_retention(paths, settings_provider())
            except Exception:
                pass

    thread = threading.Thread(target=loop, name='harness-retention', daemon=True)
    thread.start()
    return stop
