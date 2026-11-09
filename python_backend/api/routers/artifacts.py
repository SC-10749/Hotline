from __future__ import annotations

from pathlib import Path
from typing import Callable
from urllib.parse import quote

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel

from ...infrastructure.settings_store import SettingsStore
from ...modules.artifacts.store import ArtifactStore, artifact_metadata
from ...object_store import ObjectStorage

PREVIEW_CHAR_LIMIT = 20000
PREVIEW_BYTE_LIMIT = PREVIEW_CHAR_LIMIT * 4 + 4
PREVIEWABLE_TYPES = {'application/json', 'application/xml', 'application/xhtml+xml',
                     'application/javascript', 'application/yaml', 'application/x-yaml'}
DEFAULT_OWNER_HEADER = 'X-Harness-Owner'


class ArtifactCleanupPayload(BaseModel):
    retentionDays: int
    deleteFiles: bool = False


def _is_previewable(content_type: str) -> bool:
    kind = (content_type or '').split(';')[0].strip().lower()
    return (kind.startswith('text/') or kind in PREVIEWABLE_TYPES
            or kind.endswith('+json') or kind.endswith('+xml'))


def _local_file(storage: ObjectStorage, record: dict) -> Path:
    """Resolve an artifact inside generated_dir; rejects traversal and symlinked paths."""
    root = storage.settings.generated_dir.resolve()
    path = root / record['storage_key']
    resolved = path.resolve()
    if (root not in resolved.parents or not path.is_file()
            or any(part.is_symlink() for part in (path, *path.parents) if part != root)):
        raise HTTPException(status_code=404, detail='产物文件不存在或不可读')
    return resolved


def _owner_header_reader(storage: ObjectStorage,
                            settings_reader: Callable[[], dict] | None = None) -> Callable[[], str]:
    """Header name comes from the harness settings; missing store falls back to the default."""
    if settings_reader is not None:
        return lambda: str(settings_reader().get('artifactOwnerHeader') or '').strip() or DEFAULT_OWNER_HEADER
    data_dir = getattr(getattr(storage, 'settings', None), 'data_dir', None)
    if data_dir is None:
        return lambda: DEFAULT_OWNER_HEADER
    holder: dict[str, SettingsStore] = {}

    def read() -> str:
        if 'store' not in holder:
            holder['store'] = SettingsStore(Path(data_dir) / 'harness-settings.db')
        return str(holder['store'].get().get('artifactOwnerHeader') or '').strip() or DEFAULT_OWNER_HEADER

    return read


def _check_owner(request: Request, record: dict, header_name: str) -> None:
    """Ownership check for downloads: empty owner (legacy rows) is always allowed."""
    owner = str(record.get('owner') or '')
    if not owner:
        return
    supplied = request.headers.get(header_name)
    if supplied is None or not supplied.strip():
        raise HTTPException(status_code=403, detail=f'缺少归属身份请求头 {header_name}')
    if supplied.strip() != owner:
        raise HTTPException(status_code=403, detail='产物归属身份不匹配')


def create_artifact_router(store: ArtifactStore, storage: ObjectStorage,
                           settings_reader: Callable[[], dict] | None = None) -> APIRouter:
    router = APIRouter()
    owner_header = _owner_header_reader(storage, settings_reader)

    @router.get('/harness/artifacts')
    def list_artifacts(runId: str | None = None, owner: str | None = None,
                       limit: int = Query(100, ge=1, le=200), offset: int = Query(0, ge=0)):
        items, total = store.list(runId, limit, offset, owner=owner)
        return {'items': [artifact_metadata(item) for item in items], 'total': total,
                'limit': limit, 'offset': offset}

    @router.get('/harness/artifacts/{artifact_id}/download')
    def download_artifact(artifact_id: str, request: Request):
        record = store.get(artifact_id)
        if not record:
            raise HTTPException(status_code=404, detail='产物不存在')
        _check_owner(request, record, owner_header())
        if record['storage_backend'] != storage.backend:
            raise HTTPException(status_code=503, detail='产物所属存储当前未配置')
        headers = {'Cache-Control': 'private, no-store', 'X-Content-Type-Options': 'nosniff'}
        if storage.backend == 'local':
            resolved = _local_file(storage, record)
            return FileResponse(resolved, media_type=record['content_type'], filename=record['name'], headers=headers)
        try:
            response = storage.open_download(record['storage_key'])
        except Exception as exc:
            missing = getattr(exc, 'code', '') in {'NoSuchKey', 'NoSuchObject', 'NoSuchBucket'}
            raise HTTPException(status_code=404 if missing else 503,
                                detail='产物文件不存在' if missing else '产物存储暂不可用') from exc

        def chunks():
            try:
                yield from response.stream(64 * 1024)
            finally:
                response.close()
                response.release_conn()

        headers['Content-Disposition'] = f"attachment; filename*=UTF-8''{quote(record['name'], safe='')}"
        return StreamingResponse(chunks(), media_type=record['content_type'], headers=headers)

    @router.get('/harness/artifacts/{artifact_id}/preview')
    def preview_artifact(artifact_id: str, request: Request):
        record = store.get(artifact_id)
        if not record:
            raise HTTPException(status_code=404, detail='产物不存在')
        _check_owner(request, record, owner_header())
        if not _is_previewable(record['content_type']):
            raise HTTPException(status_code=415, detail='该产物类型不支持预览')
        if record['storage_backend'] != storage.backend:
            raise HTTPException(status_code=503, detail='产物所属存储当前未配置')
        if storage.backend != 'local':
            raise HTTPException(status_code=503, detail='对象存储暂不支持预览')
        data = _local_file(storage, record).read_bytes()[:PREVIEW_BYTE_LIMIT]
        content = data.decode('utf-8', errors='replace')
        truncated = len(content) > PREVIEW_CHAR_LIMIT or record['size'] > PREVIEW_BYTE_LIMIT
        return {'artifactId': record['artifact_id'], 'name': record['name'],
                'contentType': record['content_type'], 'size': record['size'],
                'truncated': truncated, 'content': content[:PREVIEW_CHAR_LIMIT]}

    @router.post('/harness/artifacts/cleanup')
    def cleanup_artifacts(payload: ArtifactCleanupPayload):
        if payload.retentionDays < 1:
            raise HTTPException(status_code=400, detail='保留天数必须大于等于 1')
        records = store.list_expired(payload.retentionDays)
        removed = store.expire(payload.retentionDays)
        if payload.deleteFiles and storage.backend == 'local':
            for record in records:
                if record['storage_backend'] != 'local':
                    continue
                try:
                    _local_file(storage, record).unlink()
                except (HTTPException, OSError):
                    continue
        return {'removed': len(removed), 'artifactIds': removed}

    return router
