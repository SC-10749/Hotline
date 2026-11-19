from typing import Literal

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from ...modules.evaluation.benchmarks import BenchmarkService


class BenchmarkRequest(BaseModel):
    kind: Literal['rag', 'bird', 'load']
    input: str = Field(default='', max_length=240)
    collect: bool = False
    databases: str = Field(default='', max_length=240)
    predictions: str = Field(default='', max_length=240)
    limit: int = Field(default=10, ge=1, le=500)
    evidence: bool = True
    profile: Literal['http', 'sse'] = 'http'
    users: int = Field(default=2, ge=1, le=100)
    duration: int = Field(default=15, ge=5, le=600)
    spawnRate: int = Field(default=1, ge=1, le=20)
    target: Literal['python', 'java'] = 'python'


def create_benchmark_router(service: BenchmarkService):
    router = APIRouter(prefix='/evaluation/benchmarks', tags=['benchmarks'])

    @router.get('/tools')
    def tools():
        return service.tools()

    @router.get('/runs')
    def runs(kind: Literal['rag', 'bird', 'load'] | None = Query(None)):
        return {'items': service.list(kind)}

    @router.post('/runs')
    def start(payload: BenchmarkRequest):
        try:
            return service.start(payload.model_dump())
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc

    @router.get('/runs/{job_id}')
    def get(job_id: str):
        try:
            return service.touch(job_id)
        except ValueError as exc:
            raise HTTPException(404, str(exc)) from exc

    @router.post('/runs/{job_id}/cancel')
    def cancel(job_id: str):
        try:
            return service.cancel(job_id)
        except ValueError as exc:
            raise HTTPException(404, str(exc)) from exc

    return router
