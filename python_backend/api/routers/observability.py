from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from fastapi import APIRouter, Query


def create_observability_router(
    list_runs: Callable[..., tuple[list[dict[str, Any]], int]],
    get_run: Callable[[str], dict[str, Any] | None],
    get_events: Callable[[str, int], list[dict[str, Any]]],
    generated_dir: Path,
) -> APIRouter:
    router = APIRouter()

    @router.get('/harness/observability/runs')
    def observability_runs(limit: int = Query(100, ge=1, le=200)):
        items, total = list_runs(limit=limit)
        return {'items': items, 'total': total}

    @router.get('/harness/observability/runs/{run_id}/events')
    def observability_events(run_id: str, after: int = Query(0, ge=0)):
        if not get_run(run_id):
            return {'items': []}
        return {'items': get_events(run_id, after)}

    @router.get('/harness/artifacts')
    def artifacts(runId: str | None = None):
        root = generated_dir.resolve()
        items: list[dict[str, Any]] = []
        if root.exists():
            for path in sorted(root.rglob('*')):
                if not path.is_file() or path.is_symlink():
                    continue
                relative = path.relative_to(root).as_posix()
                stat = path.stat()
                items.append({
                    'artifact_id': f'generated:{relative}',
                    'name': path.name,
                    'path': relative,
                    'size': stat.st_size,
                    'updated_at': stat.st_mtime,
                    'run_id': runId,
                    'download': f'/generated/{relative}',
                })
        return {'items': items}

    return router

