from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse


def create_code_map_router(directory: Path) -> APIRouter:
    router = APIRouter(prefix='/code-map', tags=['code-map'])
    assets = {
        'hotline.html': 'text/html',
        'vendor/mermaid.min.js': 'application/javascript',
    }

    def asset_file(name: str) -> Path | None:
        root = directory.resolve()
        path = (root / name).resolve()
        if path.is_relative_to(root) and path.is_file():
            return path
        return None

    @router.get('')
    def status():
        return {'available': all(asset_file(name) is not None for name in assets)}

    @router.get('/{asset_path:path}')
    def read_asset(asset_path: str):
        if asset_path not in assets:
            raise HTTPException(status_code=404, detail='代码地图资源不存在')
        path = asset_file(asset_path)
        if path is None:
            raise HTTPException(status_code=404, detail='代码地图资源不存在')
        return FileResponse(path, media_type=assets[asset_path],
                            headers={'Cache-Control': 'no-cache', 'X-Content-Type-Options': 'nosniff'})

    return router
