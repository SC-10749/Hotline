from __future__ import annotations

import shutil
from pathlib import Path, PurePosixPath
from uuid import uuid4

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from ...modules.context_engineering.privacy import private_path
from ...modules.workspaces.context import resolve_workspace_root
from ...modules.retrieval.workspace_index import workspace_files


def create_workspace_import_router(resources, directory: Path) -> APIRouter:
    router = APIRouter(tags=['workspaces'])

    @router.get('/harness/workspaces/{workspace_id}/files')
    def list_files(workspace_id: str):
        if not resources.get_workspace(workspace_id):
            raise HTTPException(404, '工作区不存在')
        root = resolve_workspace_root(resources, workspace_id)
        files = []
        if root is not None:
            for _, relative, stat in workspace_files(root, max_file_bytes=50 * 1024 * 1024):
                if len(files) == 5000:
                    return {'files': files, 'truncated': True}
                files.append({'name': relative, 'size': stat.st_size})
        return {'files': files, 'truncated': False}

    @router.post('/harness/workspaces/import')
    def import_workspace(name: str = Form(min_length=1, max_length=120),
                         files: list[UploadFile] = File(...)):
        if not name.strip() or not 1 <= len(files) <= 5000:
            raise HTTPException(400, '工作区名称或文件数量无效，最多导入 5000 个文件')
        paths = [PurePosixPath((file.filename or '').replace('\\', '/')) for file in files]
        names = [path.as_posix() for path in paths]
        if len({value.casefold() for value in names}) != len(names):
            raise HTTPException(400, '工作区包含重复路径')
        if any(private_path(value) or value in {'', '.'} for value in names):
            raise HTTPException(400, '工作区包含私密文件或不安全路径')
        directory.mkdir(parents=True, exist_ok=True)
        target = directory / uuid4().hex
        staging = directory / ('.pending-' + target.name)
        staging.mkdir()
        total = 0
        try:
            for upload, relative in zip(files, paths):
                destination = staging / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                size = 0
                with destination.open('xb') as output:
                    while chunk := upload.file.read(1024 * 1024):
                        size += len(chunk)
                        total += len(chunk)
                        if size > 50 * 1024 * 1024 or total > 512 * 1024 * 1024:
                            raise HTTPException(413, '单文件上限 50 MB，工作区导入总量上限 512 MB')
                        output.write(chunk)
            staging.rename(target)
            workspace = resources.create_workspace({'name': name.strip(), 'repository': str(target.resolve()),
                                                    'branch': 'main'})
            return {'workspace': workspace, 'files': len(files)}
        except BaseException:
            # Both paths are fresh UUID children of the explicitly supplied data directory.
            shutil.rmtree(staging, ignore_errors=True)
            shutil.rmtree(target, ignore_errors=True)
            raise
        finally:
            for upload in files:
                upload.file.close()

    return router
