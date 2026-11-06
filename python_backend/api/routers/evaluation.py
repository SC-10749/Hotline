from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from ...infrastructure.evaluation_store import EvaluationStore


class DatasetCreatePayload(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    datasetType: str = Field(default="通用", min_length=1, max_length=40)
    description: str = Field(default="", max_length=500)


class CaseCreatePayload(BaseModel):
    input: str = Field(min_length=1)
    expectedOutput: str = ""
    rubric: dict[str, Any] = Field(default_factory=dict)


class EvaluationConfigPayload(BaseModel):
    dimensions: list[dict[str, Any]] = Field(default_factory=list)
    gates: list[dict[str, Any]] = Field(default_factory=list)


class EvaluationRunPayload(BaseModel):
    datasetId: str
    agent: str = "chat"
    version: str = ""


def create_evaluation_router(store: EvaluationStore) -> APIRouter:
    router = APIRouter()

    @router.get("/evaluation/datasets")
    def list_datasets():
        return {"items": store.list_datasets()}

    @router.post("/evaluation/datasets")
    def create_dataset(payload: DatasetCreatePayload):
        return {"dataset": store.create_dataset(payload.name.strip(), payload.datasetType.strip(), payload.description.strip())}

    @router.get("/evaluation/datasets/{dataset_id}")
    def get_dataset(dataset_id: str):
        dataset = store.get_dataset(dataset_id)
        if not dataset:
            raise HTTPException(status_code=404, detail="测评集不存在")
        return {"dataset": dataset}

    @router.post("/evaluation/datasets/{dataset_id}/cases")
    def add_case(dataset_id: str, payload: CaseCreatePayload):
        case = store.add_case(dataset_id, payload.input, payload.expectedOutput, payload.rubric)
        if not case:
            raise HTTPException(status_code=404, detail="测评集不存在")
        return {"case": case}

    @router.delete("/evaluation/datasets/{dataset_id}/cases/{case_id}")
    def delete_case(dataset_id: str, case_id: str):
        if not store.delete_case(dataset_id, case_id):
            raise HTTPException(status_code=404, detail="测评样本不存在")
        return {"success": True}

    @router.put("/evaluation/datasets/{dataset_id}/cases/{case_id}")
    def update_case(dataset_id: str, case_id: str, payload: CaseCreatePayload):
        case = store.update_case(dataset_id, case_id, payload.input, payload.expectedOutput, payload.rubric)
        if not case:
            raise HTTPException(status_code=404, detail="测评样本不存在")
        return {"case": case}

    @router.get("/evaluation/config")
    def get_config():
        return {"config": store.get_config()}

    @router.put("/evaluation/config")
    def save_config(payload: EvaluationConfigPayload):
        return {"config": store.save_config(payload.model_dump())}

    @router.post("/evaluation/runs")
    def create_run(payload: EvaluationRunPayload):
        run = store.create_run(payload.datasetId, payload.agent, payload.version)
        if not run:
            raise HTTPException(status_code=404, detail="测评集不存在")
        return {"run": run, "message": "测评执行器尚未接入，已记录待执行任务"}

    @router.get("/evaluation/runs")
    def list_runs(limit: int = Query(100, ge=1, le=200)):
        return {"items": store.list_runs(limit)}

    return router

