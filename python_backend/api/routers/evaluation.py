from __future__ import annotations

import csv
import io
import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field

from pathlib import Path

from ...application.execution_service import ExecutionApplicationService, WorkerUnavailableError
from ...domain.execution import ExecutionRequest
from ...infrastructure.evaluation_store import EvaluationStore
from ...modules.evaluation import score_case
from ...modules.evaluation.analysis import (
    build_provenance,
    build_trace,
    check_gates as check_gate_rules,
    merge_traces,
    repo_commit,
    skills_digest,
)
from ...modules.evaluation.readability import classify_failure, dataset_cards
from ...modules.evaluation.simulator import next_user_message
from ...modules.execution import ActiveExecutionError
from ...modules.execution.store import event_level, event_tool

ROOT = Path(__file__).resolve().parents[3]
MAX_TRACE_EVENTS = 500


TERMINAL_EXECUTION_STATUSES = {"completed", "failed", "cancelled"}
SAMPLE_TIMEOUT_SECONDS = 120
POLL_INTERVAL_SECONDS = 0.5
BATCH_CASE_LIMIT = 500
MATRIX_RUN_LIMIT = 8

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
    turns: list[str] = Field(default_factory=list)
    userProfile: str = ""


class BatchCasePayload(BaseModel):
    input: str = ""
    expectedOutput: str = ""
    rubric: dict[str, Any] = Field(default_factory=dict)
    turns: list[str] = Field(default_factory=list)
    userProfile: str = ""


class CaseBatchPayload(BaseModel):
    cases: list[BatchCasePayload] = Field(default_factory=list)


class EvaluationConfigPayload(BaseModel):
    dimensions: list[dict[str, Any]] = Field(default_factory=list)
    gates: list[dict[str, Any]] = Field(default_factory=list)


class EvaluationRunPayload(BaseModel):
    datasetId: str
    agent: str = "chat"
    version: str = ""
    epochs: int = Field(default=1, ge=1, le=10)
    concurrency: int = Field(default=1, ge=1, le=16)
    budgetTokens: int = Field(default=0, ge=0)
    budgetSeconds: int = Field(default=0, ge=0)
    budgetSamples: int = Field(default=0, ge=0)
    pricePerMTok: float = Field(default=0.0, ge=0.0)


class GateCheckPayload(BaseModel):
    target: str = Field(min_length=1)
    base: str = ""


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


def clarify_output(events: list[dict[str, Any]]) -> str:
    """澄清轮没有正文文本，助手产出在 clarify 事件里；这里还原成一句可读的话。"""
    for item in events or []:
        event = item.get("event") if isinstance(item, dict) and "event" in item else item
        if not isinstance(event, dict) or event.get("type") != "clarify":
            continue
        content = event.get("content")
        if isinstance(content, str):
            return content
        question = str((content or {}).get("question") or "").strip()
        options = [str(item.get("label") or "").strip()
                   for item in (content or {}).get("options") or [] if item.get("label")]
        if not question and not options:
            continue
        return "【需要澄清】" + "；".join([question] + options)
    return ""


def provenance_for(dataset: dict[str, Any], payload: "EvaluationRunPayload", epochs: int) -> dict[str, Any]:
    """记录这一轮是在什么配置下跑出来的：模型、技能包 sha、代码提交。"""
    try:
        from ...config import settings
        model_name = str(getattr(settings, "model_name", "") or "")
    except Exception:
        model_name = ""
    return build_provenance(dataset=dataset, agent=payload.agent or "chat", epochs=epochs,
                            model_name=model_name, commit=repo_commit(ROOT), skills=skills_digest(ROOT))


def execute_case(svc, case: dict[str, Any], agent: str, conversation_id: str,
                 user_simulator=None, max_turns: int = 8) -> dict[str, Any]:
    """执行一个样本（可能多轮），返回最终输出、合并轨迹与执行编号。

    样本给了 turns 就按脚本走；给了用户画像就由模型扮演用户继续对话。
    """
    scripted = [str(item) for item in (case.get("turns") or []) if str(item).strip()]
    profile = str(case.get("user_profile") or "").strip()
    simulated = bool(profile) and not scripted
    queue = [str(case.get("input_text") or "")] + scripted
    limit = len(queue) if scripted else max_turns
    outputs: list[str] = []
    traces: list[dict[str, Any]] = []
    dialogue: list[dict[str, str]] = []
    exec_run_ids: list[str] = []
    status = "completed"
    error = ""
    index = 0
    while index < len(queue) and index < limit:
        utterance = queue[index]
        index += 1
        request = ExecutionRequest(conversation_id=conversation_id, agent=agent, query=utterance)
        execution = svc.create(request)
        started = time.monotonic()
        state = wait_for_run(svc, execution["run_id"])
        latency_ms = int((time.monotonic() - started) * 1000)
        events = svc.get_events(execution["run_id"]) if state["status"] == "completed" else []
        traces.append(build_trace(events, agent=agent, latency_ms=latency_ms))
        outputs.append(str(state.get("output") or "") or clarify_output(events))
        exec_run_ids.append(execution["run_id"])
        dialogue.append({"role": "user", "content": utterance})
        dialogue.append({"role": "assistant", "content": outputs[-1]})
        if state["status"] != "completed":
            status = state["status"]
            error = state.get("error") or f"样本执行状态 {state['status']}"
            break
        if simulated:
            reply = next_user_message(profile, dialogue, user_simulator)
            if not reply:
                break
            queue.append(reply)
    trace = merge_traces(traces)
    trace["turns"] = len(outputs)
    trace["transcript"] = outputs
    return {"output": outputs[-1] if outputs else "", "outputs": outputs, "trace": trace,
            "exec_run_id": exec_run_ids[-1] if exec_run_ids else "", "status": status, "error": error}


class BudgetGuard:
    """跑批预算：token 上限与运行时限。

    只决定「还领不领新任务」，不打断已经在跑的样本，所以是软上限。
    """

    def __init__(self, tokens: int = 0, seconds: int = 0, samples: int = 0):
        self.limit_tokens = max(0, int(tokens or 0))
        self.limit_seconds = max(0, int(seconds or 0))
        self.limit_samples = max(0, int(samples or 0))
        self.tokens = 0
        self.samples = 0
        self.deadline = (time.monotonic() + self.limit_seconds) if self.limit_seconds else None

    def exhausted(self) -> bool:
        if self.limit_samples and self.samples >= self.limit_samples:
            return True
        if self.limit_tokens and self.tokens >= self.limit_tokens:
            return True
        if self.deadline is not None and time.monotonic() >= self.deadline:
            return True
        return False

    def add(self, tokens: Any, sample: int = 1) -> None:
        self.tokens += max(0, int(tokens or 0))
        self.samples += max(0, int(sample or 0))

    def skip_reason(self) -> str:
        if self.limit_samples and self.samples >= self.limit_samples:
            return f"样本数预算已用尽（{self.samples}/{self.limit_samples}）"
        if self.limit_tokens and self.tokens >= self.limit_tokens:
            return f"token 预算已用尽（{self.tokens}/{self.limit_tokens}）"
        if self.deadline is not None and time.monotonic() >= self.deadline:
            return f"运行时限已到（{self.limit_seconds}s）"
        return "预算已用尽"


def execute_tasks(svc, tasks: list[tuple[dict[str, Any], int]], agent: str, eval_run_id: str,
                  concurrency: int, budget: BudgetGuard, user_simulator=None
                  ) -> tuple[list[Any], str]:
    """并发执行样本任务。

    返回与任务顺序一致的列表：元素是执行结果、异常对象，或 None（因预算未执行）。
    第二个返回值是整轮中止原因（空串表示正常跑完）。
    """
    results: list[Any] = [None] * len(tasks)
    state = {"next": 0, "abort": ""}
    lock = threading.Lock()

    def worker() -> None:
        while True:
            with lock:
                if state["abort"] or state["next"] >= len(tasks) or budget.exhausted():
                    return
                index = state["next"]
                state["next"] += 1
            case, epoch = tasks[index]
            conversation_id = f"eval:{eval_run_id}:{case['case_id']}:{epoch}"
            try:
                outcome = execute_case(svc, case, agent, conversation_id, user_simulator)
            except ValueError as exc:
                with lock:
                    state["abort"] = str(exc)
                return
            except WorkerUnavailableError as exc:
                with lock:
                    state["abort"] = f"执行服务不可用：{exc}"
                return
            except Exception as exc:  # 单个样本出错不影响其它样本
                results[index] = exc
                continue
            results[index] = outcome
            budget.add((outcome.get("trace") or {}).get("tokens") or 0)

    if concurrency <= 1:
        worker()
    else:
        with ThreadPoolExecutor(max_workers=concurrency) as pool:
            for future in [pool.submit(worker) for _ in range(concurrency)]:
                future.result()
    return results, state["abort"]


def summarize_results(results: list[dict[str, Any]], case_count: int,
                      epochs: int = 1, failed: int = 0, budget: BudgetGuard | None = None,
                      concurrency: int = 1, price_per_mtok: float = 0.0) -> dict[str, Any]:
    """把样本结果汇总成运行摘要；含重复执行的稳定性指标。"""
    passed = sum(1 for item in results if item.get("verdict") == "passed")
    scorer_unavailable = sum(1 for item in results if item.get("verdict") == "scorer_unavailable")
    by_case: dict[str, list[str]] = {}
    for item in results:
        verdict = str(item.get("verdict") or "")
        if verdict == "skipped":
            # 被预算跳过的样本没参与评估，不该拉低 passAtK / flakyRate。
            continue
        by_case.setdefault(str(item.get("case_id") or ""), []).append(verdict)
    total = len(by_case) or case_count
    pass_at_k = sum(1 for verdicts in by_case.values() if verdicts and all(v == "passed" for v in verdicts))
    flaky = sum(1 for verdicts in by_case.values() if len(set(verdicts)) > 1)
    latencies = [item.get("latencyMs") for item in
                 ((item.get("trace") or {}) for item in results)
                 if isinstance(item.get("latencyMs"), (int, float))]
    tokens = [item.get("tokens") for item in
              ((item.get("trace") or {}) for item in results)
              if isinstance(item.get("tokens"), (int, float))]
    turn_counts = [int(((item.get("trace") or {}).get("counts") or {}).get("turns") or 0)
                   for item in results]
    failure_kinds: dict[str, int] = {}
    for item in results:
        kind = str(item.get("failure_kind") or "")
        if kind:
            failure_kinds[kind] = failure_kinds.get(kind, 0) + 1
    result_count = len(results)
    skipped = sum(1 for item in results if item.get("verdict") == "skipped")
    scored = result_count - skipped
    tokens_used = int((budget.tokens if budget else 0) or 0)
    return {
        "caseCount": case_count,
        "resultCount": result_count,
        "passedCount": passed,
        "failedCount": failed + scorer_unavailable,
        "passRate": round(passed / scored, 4) if scored else 0.0,
        "concurrency": max(1, int(concurrency or 1)),
        "budgetTokens": int(budget.limit_tokens if budget else 0),
        "budgetSeconds": int(budget.limit_seconds if budget else 0),
        "budgetSamples": int(budget.limit_samples if budget else 0),
        "tokensUsed": tokens_used,
        "budgetExhausted": skipped > 0,
        "skippedCount": skipped,
        "pricePerMTok": round(float(price_per_mtok or 0.0), 6),
        "estimatedCostUsd": (round(tokens_used / 1_000_000 * float(price_per_mtok), 6)
                              if price_per_mtok else 0.0),
        "epochs": max(1, int(epochs or 1)),
        "passAtK": round(pass_at_k / total, 4) if total else 0.0,
        "flakyRate": round(flaky / total, 4) if total else 0.0,
        "avgLatencyMs": round(sum(latencies) / len(latencies), 1) if latencies else 0.0,
        "avgTokens": round(sum(tokens) / len(tokens), 1) if tokens else 0.0,
        "avgTurns": round(sum(turn_counts) / len(turn_counts), 2) if turn_counts else 0.0,
        "failureKinds": failure_kinds,
    }


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
                              execution_service: ExecutionApplicationService | None = None,
                              user_simulator=None) -> APIRouter:
    router = APIRouter()
    from .benchmarks import create_benchmark_router
    from ...modules.evaluation.benchmarks import BenchmarkService
    benchmarks = BenchmarkService(store.path.parent)
    router.include_router(create_benchmark_router(benchmarks))
    router.benchmark_service = benchmarks

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
        epochs = max(1, min(int(payload.epochs or 1), 10))
        if run is None:
            run = store.create_run(payload.datasetId, payload.agent or "chat", payload.version,
                                   status="running", epochs=epochs, provenance=provenance_for(dataset, payload, epochs))
        eval_run_id = run["eval_run_id"]
        if not cases:
            store.update_run(eval_run_id, "blocked", error="测评集没有样本，未执行")
            return store.get_run(eval_run_id), []
        try:
            svc = service()
        except Exception as exc:  # pragma: no cover - defensive, misconfigured service
            store.update_run(eval_run_id, "blocked", error=f"执行服务不可用：{exc}")
            return store.get_run(eval_run_id), []
        concurrency = max(1, min(int(payload.concurrency or 1), 16))
        budget = BudgetGuard(payload.budgetTokens, payload.budgetSeconds, payload.budgetSamples)
        tasks = [(case, epoch) for case in cases for epoch in range(epochs)]
        outcomes, abort = execute_tasks(svc, tasks, payload.agent or "chat", eval_run_id,
                                       concurrency, budget, user_simulator)
        if abort:
            store.update_run(eval_run_id, "blocked", error=abort)
            return store.get_run(eval_run_id), store.list_results(eval_run_id)
        failed = 0
        for index, (case, epoch) in enumerate(tasks):
            outcome = outcomes[index]
            if outcome is None:
                # 预算或时限用尽：这个样本没跑，记为已跳过，不算失败。
                store.save_result(eval_run_id, case["case_id"], 0.0, "skipped", budget.skip_reason(), "",
                                  epoch=epoch, failure_kind="budget_exhausted")
                continue
            if isinstance(outcome, Exception):
                failed += 1
                store.save_result(eval_run_id, case["case_id"], 0.0, "failed", str(outcome), "",
                                  epoch=epoch, failure_kind="execution_error")
                continue
            trace = outcome["trace"]
            if outcome["status"] != "completed":
                failed += 1
                verdict = "timeout" if outcome["status"] == "timeout" else "failed"
                store.save_result(eval_run_id, case["case_id"], 0.0, verdict, outcome["error"],
                                  outcome["output"], epoch=epoch,
                                  failure_kind=classify_failure(verdict, case.get("rubric"), trace,
                                                             outcome.get("output", ""),
                                                             case.get("expected_output", "")),
                                  exec_run_id=outcome["exec_run_id"], trace=trace)
                continue
            scored = score_case(outcome["output"], case["expected_output"], case["rubric"], trace=trace)
            store.save_result(eval_run_id, case["case_id"], scored["score"], scored["verdict"],
                              scored["detail"], outcome["output"], epoch=epoch,
                              failure_kind=classify_failure(scored["verdict"], case.get("rubric"), trace,
                                                         outcome.get("output", ""),
                                                         case.get("expected_output", "")),
                              exec_run_id=outcome["exec_run_id"], trace=trace,
                              metrics=scored.get("metrics"))
        results = store.list_results(eval_run_id)
        # 模型评分不可用的样本记 0 分并计入失败数，但整轮测评照常结束；
        # 没有 model 类型规则时，统计口径与原来完全一致。
        summary = summarize_results(results, len(cases), epochs, failed, budget,
                                    concurrency, float(payload.pricePerMTok or 0.0))
        # 测评照常结束：模型评分不可用只影响样本本身，不把整轮标成失败。
        store.update_run(
            eval_run_id,
            "failed" if failed else "completed",
            error=f"{failed} 个样本未正常执行" if failed else None,
            summary=summary,
        )
        return store.get_run(eval_run_id), results

    @router.get("/evaluation/semantic-metrics")
    def semantic_metrics():
        """内置语义指标模板，供样本编辑时选择。"""
        from ...modules.evaluation.semantics import semantic_templates
        return {"items": semantic_templates()}

    @router.get("/evaluation/datasets")
    def list_datasets():
        """测评集列表带上最近一次运行的摘要，页面不用再自己猜状态。"""
        return {"items": dataset_cards(store.list_datasets(), store.list_runs(200))}

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
        case = store.add_case(dataset_id, payload.input, payload.expectedOutput, payload.rubric,
                                payload.turns, payload.userProfile)
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
        case = store.update_case(dataset_id, case_id, payload.input, payload.expectedOutput,
                                  payload.rubric, payload.turns, payload.userProfile)
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
        run = store.create_run(payload.datasetId, payload.agent or "chat", payload.version,
                               status="running", epochs=max(1, min(int(payload.epochs or 1), 10)),
                               provenance=provenance_for(dataset, payload, max(1, min(int(payload.epochs or 1), 10))))
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
            summary = summarize_results(results, len(results), int(run.get("epochs") or 1))
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

    @router.get("/evaluation/runs/matrix")
    def run_matrix(runs: str = Query(...)):
        """多 run × 样本的并排矩阵；runs 里第一个是基线。"""
        from ...modules.evaluation.matrix import build_matrix

        run_ids = [item.strip() for item in str(runs or "").split(",") if item.strip()]
        if len(run_ids) < 2:
            raise HTTPException(status_code=400, detail="矩阵至少需要两个测评运行")
        if len(run_ids) > MATRIX_RUN_LIMIT:
            raise HTTPException(status_code=400, detail=f"矩阵最多支持 {MATRIX_RUN_LIMIT} 个测评运行")
        found = []
        for run_id in run_ids:
            run = store.get_run(run_id)
            if not run:
                raise HTTPException(status_code=404, detail=f"测评运行不存在：{run_id}")
            found.append(run)
        results_by_run = {run_id: store.list_results(run_id) for run_id in run_ids}
        return build_matrix(found, results_by_run)

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
        writer.writerow(["case_id", "score", "verdict", "detail", "actual_output", "created_at",
                         "epoch", "failure_kind", "latency_ms", "tokens"])
        for item in results:
            trace = item.get("trace") or {}
            writer.writerow([
                item["case_id"], item["score"], item["verdict"], item["detail"],
                item["actual_output"], item["created_at"], item.get("epoch", 0),
                item.get("failure_kind", ""), trace.get("latencyMs", ""), trace.get("tokens", ""),
            ])
        return Response(
            content="\ufeff" + buffer.getvalue(),
            media_type="text/csv",
            headers={"Content-Disposition": f'attachment; filename="{eval_run_id}.csv"'},
        )

    @router.get("/evaluation/runs/{eval_run_id}/trace")
    def run_trace(eval_run_id: str, caseId: str = Query(...), epoch: int = Query(0, ge=0)):
        if not store.get_run(eval_run_id):
            raise HTTPException(status_code=404, detail="测评运行不存在")
        result = store.find_result(eval_run_id, caseId, epoch)
        if not result:
            raise HTTPException(status_code=404, detail="测评样本不存在")
        trace = dict(result.get("trace") or {})
        events: list[dict[str, Any]] = []
        exec_run_id = str(result.get("exec_run_id") or "")
        if exec_run_id:
            try:
                raw = service().get_events(exec_run_id)
            except Exception:
                raw = []
            for item in raw[:MAX_TRACE_EVENTS]:
                event = item.get("event") or {}
                content = event.get("content")
                text = content if isinstance(content, str) else (
                    "" if content is None else json.dumps(content, ensure_ascii=False))
                events.append({
                    "event_id": item.get("event_id"),
                    "created_at": item.get("created_at"),
                    "type": event.get("type") or "",
                    "level": event_level(event),
                    "tool": event_tool(event),
                    "summary": " ".join(text.split())[:200],
                })
        trace.update({"caseId": caseId, "epoch": epoch, "events": events})
        return {"trace": trace}

    @router.post("/evaluation/gates/check")
    def gates_check(payload: GateCheckPayload):
        run = store.get_run(payload.target)
        if not run:
            raise HTTPException(status_code=404, detail="测评运行不存在")
        base_summary = None
        if payload.base:
            base_run = store.get_run(payload.base)
            if not base_run:
                raise HTTPException(status_code=404, detail=f"基线测评运行不存在：{payload.base}")
            base_summary = run_metrics(base_run, store.list_results(payload.base))
        config = store.get_config()
        report = check_gate_rules(config.get("gates") or [], run.get("summary") or {}, base_summary)
        return {**report, "config": config}

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
