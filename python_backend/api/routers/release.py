from __future__ import annotations

from typing import Any, Callable

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from ...infrastructure.governance_store import GovernanceStore


class ReleaseActionPayload(BaseModel):
    project: str
    name: str
    version: str | None = None
    percentage: int = Field(default=10, ge=0, le=100)
    gate: dict[str, Any] | None = None


class ReleaseMetricPayload(BaseModel):
    project: str
    name: str
    version: str
    metric: str
    value: float
    requestId: str | None = None


class ReleaseGatePayload(BaseModel):
    e2ePassRate: float = Field(ge=0, le=1)
    ragFaithfulness: float = Field(ge=0, le=1)
    highRiskErrors: int = Field(ge=0)
    evalRunId: str | None = None
    project: str = ''
    name: str = ''
    version: str = ''


def create_release_router(run_catalog: Callable[[str, dict[str, Any]], dict[str, Any]], default_project: str, evaluation_run_exists: Callable[[str], dict[str, Any] | None] | None = None, gate_store: GovernanceStore | None = None) -> APIRouter:
    router = APIRouter()

    def project_value(value: str | None) -> str:
        return value.strip() if value and value.strip() else default_project

    def call(action: str, args: dict[str, Any]):
        try:
            return run_catalog(action, args)
        except (ValueError, KeyError, TypeError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    def gate_result(payload: dict[str, Any]) -> dict[str, Any]:
        checks = {
            'e2ePassRate': float(payload.get('e2ePassRate', 0)) >= 0.90,
            'ragFaithfulness': float(payload.get('ragFaithfulness', 0)) >= 0.85,
            'highRiskErrors': int(payload.get('highRiskErrors', 1)) == 0,
        }
        if payload.get('evalRunId') and evaluation_run_exists:
            checks['evalRunId'] = evaluation_run_exists(str(payload['evalRunId'])) is not None
        return {'passed': all(checks.values()), 'checks': checks, 'thresholds': {'e2ePassRate': 0.90, 'ragFaithfulness': 0.85, 'highRiskErrors': 0}}

    @router.get("/release/summary")
    def release_summary(project: str | None = None):
        selected = project_value(project)
        return {
            "project": selected,
            "rollouts": call("rollouts", {}).get("rollouts", []),
            "runs": call("evolution_runs", {}).get("runs", []),
            "metrics": call("metrics", {}).get("metrics", []),
        }

    @router.get("/release/rollouts")
    def list_rollouts():
        return call("rollouts", {})

    @router.get("/release/runs")
    def list_release_runs():
        return call("evolution_runs", {})

    @router.get("/release/metrics")
    def list_metrics(limit: int = Query(200, ge=1, le=500)):
        rows = call("metrics", {}).get("metrics", [])
        return {"metrics": rows[:limit]}

    @router.get("/release/gates")
    def list_gates(limit: int = Query(100, ge=1, le=200)):
        return {"items": gate_store.list_gates(limit) if gate_store else []}

    @router.post("/release/promote")
    def promote(payload: ReleaseActionPayload):
        if not payload.gate or not gate_result(payload.gate)['passed']:
            raise HTTPException(status_code=412, detail='发布前质量门禁未通过')
        return call("promote", {"project": project_value(payload.project), "name": payload.name, "version": payload.version, "percentage": payload.percentage})

    @router.post("/release/gate")
    def evaluate_gate(payload: ReleaseGatePayload):
        result = gate_result(payload.model_dump())
        if gate_store:
            result['gate'] = gate_store.save_gate({**payload.model_dump(), **result, 'project': project_value(payload.project)})
        return result

    @router.post("/release/rollback")
    def rollback(payload: ReleaseActionPayload):
        return call("rollback", {"project": project_value(payload.project), "name": payload.name})

    @router.post("/release/metrics")
    def record_metric(payload: ReleaseMetricPayload):
        return call("metric", payload.model_dump())

    return router

