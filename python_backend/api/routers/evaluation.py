from __future__ import annotations

import csv
import io
import threading
import time
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field

from ...application.execution_service import ExecutionApplicationService, WorkerUnavailableError
from ...domain.execution import ExecutionRequest
from ...infrastructure.evaluation_store import EvaluationStore
from ...modules.evaluation import score_case
from ...modules.execution import ActiveExecutionError


TERMINAL_EXECUTION_STATUSES = {"completed", "failed", "cancelled"}
SAMPLE_TIMEOUT_SECONDS = 120
POLL_INTERVAL_SECONDS = 0.5
BATCH_CASE_LIMIT = 500

# 后台执行的测评线程登记处：进程退出或测试清理前需要等它们结束，
# 否则线程仍持有 SQLite 文件句柄会导致临时目录删除失败。
_BACKGROUND_THREADS: set[threading.Thread] = set()


def wait_for_background_runs(timeout: float = 30.0) -> None:
    """等待所有后台测评线程结束。"""
    deadline = time.monotonic() + max(0.0, timeout)
    while True:
        alive = [thread for thread in _BACKGROUND_THREADS if thread.is_alive()]
        if not alive:
            break
        if time.monotonic() >= deadline:
            break
        for thread in alive:
            thread.join(timeout=1)


class DatasetCreatePayload(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    datasetType: str = Field(default="通用", min_length=1, max_length=40)
    description: str = Field(default="", max_length=500)


class CaseCreatePayload(BaseModel):
    input: str = Field(min_length=1)
    expectedOutput: str = ""
    rubric: dict[str, Any] = Field(default_factory=dict)


class BatchCasePayload(BaseModel):
    input: str = ""
    expectedOutput: str = ""
    rubric: dict[str, Any] = Field(default_factory=dict)


class CaseBatchPayload(BaseModel):
    cases: list[BatchCasePayload] = Field(default_factory=list)


class EvaluationConfigPayload(BaseModel):
    dimensions: list[dict[str, Any]] = Field(default_factory=list)
    gates: list[dict[str, Any]] = Field(default_factory=list)


class EvaluationRunPayload(BaseModel):
    datasetId: str
    agent: str = "chat"
    version: str = ""


class ReplayPayload(BaseModel):
    caseIds: list[str] = Field(default_factory=list)


def collect_output(service: ExecutionApplicationService, run_id: str) -> str:
    """Join the text events of one execution run into the model answer."""
    chunks: list[str] = []
    for item in service.get_events(run_id):
        event = item.get("event") or {}
        if event.get("type") == "text":
            chunks.append(str(event.get("content") or ""))
    return "".join(chunks)


def wait_for_run(service: ExecutionApplicationService, run_id: str,
                 timeout: float = SAMPLE_TIMEOUT_SECONDS) -> dict[str, Any]:
    """Wait until the execution run reaches a terminal state."""
    deadline = time.monotonic() + timeout
    while True:
        current = service.get_run(run_id)
        status = current.get("status") if current else None
        if status in TERMINAL_EXECUTION_STATUSES:
            return {
                "status": status,
                "output": collect_output(service, run_id),
                "error": (current or {}).get("error"),
            }
        if time.monotonic() >= deadline:
            return {"status": "timeout", "output": "", "error": "样本执行超时"}
        time.sleep(POLL_INTERVAL_SECONDS)


def create_evaluation_router(store: EvaluationStore,
                              execution_service: ExecutionApplicationService | None = None) -> APIRouter:
    router = APIRouter()

    def service() -> ExecutionApplicationService:
        nonlocal execution_service
        if execution_service is None:
            from ...config import settings
            from ...infrastructure.queue.sqlite import SqliteExecutionQueue
            execution_service = ExecutionApplicationService(SqliteExecutionQueue(settings.execution_db_path))
        return execution_service

    def run_evaluation(payload: EvaluationRunPayload,
                       run: dict[str, Any] | None = None) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        dataset = store.get_dataset(payload.datasetId)
        if not dataset:
            raise HTTPException(status_code=404, detail="测评集不存在")
        cases = dataset.get("cases") or []
        if run is None:
            run = store.create_run(payload.datasetId, payload.agent or "chat", payload.version, status="running")
        eval_run_id = run["eval_run_id"]
        if not cases:
            store.update_run(eval_run_id, "blocked", error="测评集没有样本，未执行")
            return store.get_run(eval_run_id), []
        try:
            svc = service()
        except Exception as exc:  # pragma: no cover - defensive, misconfigured service
            store.update_run(eval_run_id, "blocked", error=f"执行服务不可用：{exc}")
            return store.get_run(eval_run_id), []
        failed = 0
        for case in cases:
            try:
                request = ExecutionRequest(
                    conversation_id=f"eval:{eval_run_id}:{case['case_id']}",
                    agent=payload.agent or "chat",
                    query=case["input_text"],
                )
            except ValueError as exc:
                store.update_run(eval_run_id, "blocked", error=str(exc))
                return store.get_run(eval_run_id), store.list_results(eval_run_id)
            try:
                execution = svc.create(request)
            except WorkerUnavailableError as exc:
                store.update_run(eval_run_id, "blocked", error=f"执行服务不可用：{exc}")
                return store.get_run(eval_run_id), store.list_results(eval_run_id)
            except ActiveExecutionError as exc:
                failed += 1
                store.save_result(eval_run_id, case["case_id"], 0.0, "failed", str(exc), "")
                continue
            state = wait_for_run(svc, execution["run_id"])
            if state["status"] != "completed":
                failed += 1
                verdict = "timeout" if state["status"] == "timeout" else "failed"
                detail = state.get("error") or f"样本执行状态 {state['status']}"
                store.save_result(eval_run_id, case["case_id"], 0.0, verdict, detail, state.get("output", ""))
                continue
            scored = score_case(state["output"], case["expected_output"], case["rubric"])
            store.save_result(eval_run_id, case["case_id"], scored["score"], scored["verdict"],
                              scored["detail"], state["output"])
        results = store.list_results(eval_run_id)
        passed = sum(1 for item in results if item["verdict"] == "passed")
        # 模型评分不可用的样本记 0 分并计入失败数，但整轮测评照常结束；
        # 没有 model 类型规则时，统计口径与原来完全一致。
        scorer_unavailable = sum(1 for item in results if item["verdict"] == "scorer_unavailable")
        summary = {
            "caseCount": len(cases),
            "passedCount": passed,
            "failedCount": failed + scorer_unavailable,
            "passRate": round(passed / len(cases), 4) if cases else 0.0,
        }
        # 测评照常结束：模型评分不可用只影响样本本身，不把整轮标成失败。
        store.update_run(
            eval_run_id,
            "failed" if failed else "completed",
            error=f"{failed} 个样本未正常执行" if failed else None,
            summary=summary,
        )
        return store.get_run(eval_run_id), results

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

    @router.delete("/evaluation/datasets/{dataset_id}")
    def delete_dataset(dataset_id: str):
        if not store.delete_dataset(dataset_id):
            raise HTTPException(status_code=404, detail="测评集不存在")
        return {"success": True}

    @router.post("/evaluation/datasets/{dataset_id}/cases")
    def add_case(dataset_id: str, payload: CaseCreatePayload):
        case = store.add_case(dataset_id, payload.input, payload.expectedOutput, payload.rubric)
        if not case:
            raise HTTPException(status_code=404, detail="测评集不存在")
        return {"case": case}

    @router.post("/evaluation/datasets/{dataset_id}/cases/batch")
    def add_cases(dataset_id: str, payload: CaseBatchPayload):
        if not payload.cases:
            raise HTTPException(status_code=400, detail="批量导入样本不能为空")
        if len(payload.cases) > BATCH_CASE_LIMIT:
            raise HTTPException(status_code=400, detail=f"批量导入最多 {BATCH_CASE_LIMIT} 条样本")
        if any(not item.input.strip() for item in payload.cases):
            raise HTTPException(status_code=400, detail="样本输入不能为空")
        cases = store.add_cases(dataset_id, [item.model_dump() for item in payload.cases])
        if cases is None:
            raise HTTPException(status_code=404, detail="测评集不存在")
        return {"created": len(cases), "cases": cases}

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

    @router.post("/evaluation/datasets/{dataset_id}/snapshots")
    def create_snapshot(dataset_id: str):
        snapshot = store.create_snapshot(dataset_id)
        if not snapshot:
            raise HTTPException(status_code=404, detail="测评集不存在")
        return {"snapshot": snapshot}

    @router.get("/evaluation/datasets/{dataset_id}/snapshots")
    def list_snapshots(dataset_id: str):
        return {"items": store.list_snapshots(dataset_id)}

    @router.get("/evaluation/config")
    def get_config():
        return {"config": store.get_config()}

    @router.put("/evaluation/config")
    def save_config(payload: EvaluationConfigPayload):
        return {"config": store.save_config(payload.model_dump())}

    def run_in_background(payload: EvaluationRunPayload, run: dict[str, Any]) -> None:
        try:
            run_evaluation(payload, run)
        except Exception as exc:  # pragma: no cover - defensive
            try:
                store.update_run(run["eval_run_id"], "failed", error=f"测评执行失败：{exc}")
            except Exception:
                pass

    @router.post("/evaluation/runs")
    def create_run(payload: EvaluationRunPayload):
        dataset = store.get_dataset(payload.datasetId)
        if not dataset:
            raise HTTPException(status_code=404, detail="测评集不存在")
        run = store.create_run(payload.datasetId, payload.agent or "chat", payload.version, status="running")
        if not (dataset.get("cases") or []):
            store.update_run(run["eval_run_id"], "blocked", error="测评集没有样本，未执行")
            return {"run": store.get_run(run["eval_run_id"]), "results": [], "message": "测评集没有样本，未执行"}
        # 测评会逐样本跑真实执行，耗时可能超过请求超时，所以放到后台线程执行。
        thread = threading.Thread(target=run_in_background, args=(payload, run), daemon=True)
        _BACKGROUND_THREADS.add(thread)
        thread.start()
        return {"run": store.get_run(run["eval_run_id"]), "results": [],
                "message": "测评已开始，可用测评运行编号查询进度"}

    @router.get("/evaluation/runs")
    def list_runs(limit: int = Query(100, ge=1, le=200)):
        return {"items": store.list_runs(limit)}

    def run_metrics(run: dict[str, Any], results: list[dict[str, Any]]) -> dict[str, Any]:
        """从样本结果算出汇总指标；run.summary 缺失时回退到结果统计。"""
        summary = run.get("summary")
        if not isinstance(summary, dict) or "caseCount" not in summary:
            passed = sum(1 for item in results if item["verdict"] == "passed")
            summary = {
                "caseCount": len(results),
                "passedCount": passed,
                "failedCount": len(results) - passed,
                "passRate": round(passed / len(results), 4) if results else 0.0,
            }
        return summary

    @router.get("/evaluation/runs/compare")
    def compare_runs(base: str = Query(...), target: str = Query(...)):
        base_run = store.get_run(base)
        if not base_run:
            raise HTTPException(status_code=404, detail=f"基线测评运行不存在：{base}")
        target_run = store.get_run(target)
        if not target_run:
            raise HTTPException(status_code=404, detail=f"对比测评运行不存在：{target}")
        base_results = store.list_results(base)
        target_results = store.list_results(target)
        base_summary = run_metrics(base_run, base_results)
        target_summary = run_metrics(target_run, target_results)

        summary_diff = {}
        for key in ("caseCount", "passedCount", "failedCount", "passRate"):
            before = base_summary.get(key) or 0
            after = target_summary.get(key) or 0
            summary_diff[key] = {"base": before, "target": after, "delta": round(float(after) - float(before), 4)}

        base_by_case = {item["case_id"]: item for item in base_results}
        target_by_case = {item["case_id"]: item for item in target_results}
        cases = []
        for case_id in sorted(set(base_by_case) | set(target_by_case)):
            before = base_by_case.get(case_id)
            after = target_by_case.get(case_id)
            if before and after:
                before_passed = before["verdict"] == "passed"
                after_passed = after["verdict"] == "passed"
                if after_passed and not before_passed:
                    change = "improved"
                elif before_passed and not after_passed:
                    change = "regressed"
                else:
                    change = "unchanged"
            elif after:
                change = "added"
            else:
                change = "removed"
            cases.append({
                "caseId": case_id,
                "change": change,
                "base": before and {"verdict": before["verdict"], "score": before["score"]},
                "target": after and {"verdict": after["verdict"], "score": after["score"]},
            })

        return {
            "sameDataset": base_run.get("dataset_id") == target_run.get("dataset_id"),
            "base": {"evalRunId": base, "datasetId": base_run.get("dataset_id"), "summary": base_summary},
            "target": {"evalRunId": target, "datasetId": target_run.get("dataset_id"), "summary": target_summary},
            "summaryDiff": summary_diff,
            "cases": cases,
        }

    @router.get("/evaluation/runs/{eval_run_id}/export")
    def export_run(eval_run_id: str, format: str = Query("json", pattern="^(csv|json)$")):
        run = store.get_run(eval_run_id)
        if not run:
            raise HTTPException(status_code=404, detail="测评运行不存在")
        results = store.list_results(eval_run_id)
        if format == "json":
            return {"run": run, "results": results}
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(["case_id", "score", "verdict", "detail", "actual_output", "created_at"])
        for item in results:
            writer.writerow([
                item["case_id"], item["score"], item["verdict"], item["detail"],
                item["actual_output"], item["created_at"],
            ])
        return Response(
            content="\ufeff" + buffer.getvalue(),
            media_type="text/csv",
            headers={"Content-Disposition": f'attachment; filename="{eval_run_id}.csv"'},
        )

    @router.get("/evaluation/runs/{eval_run_id}")
    def get_run(eval_run_id: str):
        run = store.get_run(eval_run_id)
        if not run:
            raise HTTPException(status_code=404, detail="测评运行不存在")
        return {"run": run, "results": store.list_results(eval_run_id)}

    @router.post("/evaluation/runs/{eval_run_id}/replay")
    def replay(eval_run_id: str, payload: ReplayPayload | None = None):
        run = store.get_run(eval_run_id)
        if not run:
            raise HTTPException(status_code=404, detail="测评运行不存在")
        wanted = set(payload.caseIds) if payload and payload.caseIds else None
        failed = [item for item in store.list_results(eval_run_id)
                  if item["verdict"] in {"failed", "timeout"}
                  and (wanted is None or item["case_id"] in wanted)]
        if not failed:
            return {"runs": []}
        dataset = store.get_dataset(run["dataset_id"]) or {}
        cases = {case["case_id"]: case for case in dataset.get("cases") or []}
        svc = service()
        items = []
        for item in failed:
            case = cases.get(item["case_id"])
            if not case:
                continue
            try:
                request = ExecutionRequest(
                    conversation_id=f"eval:{eval_run_id}:replay:{item['case_id']}:{uuid4().hex[:6]}",
                    agent=run.get("agent") or "chat",
                    query=case["input_text"],
                )
                execution = svc.create(request)
            except WorkerUnavailableError as exc:
                raise HTTPException(status_code=503, detail=str(exc)) from exc
            except ActiveExecutionError as exc:
                raise HTTPException(status_code=409, detail=str(exc)) from exc
            items.append({
                "caseId": item["case_id"],
                "runId": execution["run_id"],
                "status": execution.get("status", "queued"),
            })
        return {"runs": items}

    return router
