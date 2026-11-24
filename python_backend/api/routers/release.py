from __future__ import annotations

import json
import logging
import os
import threading
from typing import Any, Callable

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from ...infrastructure.governance_store import (
    DEFAULT_RELEASE_CONFIG,
    GATE_THRESHOLD_KEYS,
    RELEASE_CONFIG_KEYS,
    GovernanceStore,
)

logger = logging.getLogger(__name__)

OBSERVATION_INTERVAL_ENV = "HARNESS_ROLLOUT_OBSERVE_INTERVAL"
DEFAULT_OBSERVATION_INTERVAL = 60.0
MIN_OBSERVATION_INTERVAL = 15.0

# 后台灰度观察线程：模块级登记，应用退出或测试清理前需要停掉。
_OBSERVATION_LOCK = threading.Lock()
_OBSERVATION_THREAD: threading.Thread | None = None
_OBSERVATION_STOP: threading.Event = threading.Event()
_OBSERVATION_OBSERVERS: list[Callable[[], None]] = []


def observation_interval() -> float:
    """观察间隔（秒），可用环境变量调整，下限 15 秒。"""
    raw = os.getenv(OBSERVATION_INTERVAL_ENV, "").strip()
    try:
        value = float(raw) if raw else DEFAULT_OBSERVATION_INTERVAL
    except ValueError:
        value = DEFAULT_OBSERVATION_INTERVAL
    return max(MIN_OBSERVATION_INTERVAL, value)


def stop_release_observation(timeout: float = 5.0) -> None:
    """停止后台灰度观察线程（应用退出、测试清理时调用）。"""
    global _OBSERVATION_THREAD
    with _OBSERVATION_LOCK:
        thread = _OBSERVATION_THREAD
        _OBSERVATION_THREAD = None
        _OBSERVATION_OBSERVERS.clear()
        stop_event = _OBSERVATION_STOP
        stop_event.set()
    if thread and thread.is_alive():
        thread.join(timeout)


def run_release_observation_once() -> list[Any]:
    """立即执行一轮灰度观察（定时线程与手动触发共用）。"""
    results: list[Any] = []
    for observer in list(_OBSERVATION_OBSERVERS):
        try:
            results.append(observer())
        except Exception as exc:  # pragma: no cover - 单个观察失败不影响其它观察
            logger.warning("灰度观察失败：%s", exc)
    return results


def _observation_loop(stop_event: threading.Event) -> None:
    while not stop_event.wait(observation_interval()):
        run_release_observation_once()


# 兼容别名：观察线程也可以用这个名字停止。
stop_observation_loop = stop_release_observation


def _register_observer(observer: Callable[[], None]) -> None:
    """登记观察回调并确保观察线程在运行。"""
    global _OBSERVATION_THREAD, _OBSERVATION_STOP
    with _OBSERVATION_LOCK:
        _OBSERVATION_OBSERVERS.append(observer)
        if _OBSERVATION_THREAD and _OBSERVATION_THREAD.is_alive():
            return
        stop_event = threading.Event()
        _OBSERVATION_STOP = stop_event
        thread = threading.Thread(target=_observation_loop, args=(stop_event,), name="harness-rollout-observation", daemon=True)
        _OBSERVATION_THREAD = thread
        thread.start()


class ReleaseActionPayload(BaseModel):
    project: str
    name: str
    version: str | None = None
    percentage: int = Field(default=10, ge=0, le=100)
    gate: dict[str, Any] | None = None
    operator: str | None = None


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


class ReleaseRolloutAdvancePayload(BaseModel):
    project: str = ''
    name: str
    version: str | None = None
    percentage: int = Field(ge=0, le=100)
    operator: str | None = None


class ReleaseObservePayload(BaseModel):
    project: str = ''
    name: str
    version: str | None = None


class ReleaseConfigPayload(BaseModel):
    rolloutErrorThreshold: float = Field(ge=0, le=1)
    rolloutMinSamples: int = Field(ge=0)
    autoRollback: bool = True


class GateThresholdPayload(BaseModel):
    e2ePassRate: float = Field(ge=0, le=1)
    ragFaithfulness: float = Field(ge=0, le=1)
    highRiskErrors: int = Field(ge=0)


def create_release_router(run_catalog: Callable[[str, dict[str, Any]], dict[str, Any]], default_project: str, evaluation_run_exists: Callable[[str], dict[str, Any] | None] | None = None, gate_store: GovernanceStore | None = None) -> APIRouter:
    router = APIRouter()

    def project_value(value: str | None) -> str:
        return value.strip() if value and value.strip() else default_project

    def call(action: str, args: dict[str, Any]):
        try:
            return run_catalog(action, args)
        except (ValueError, KeyError, TypeError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    def release_config() -> dict[str, Any]:
        if gate_store:
            return gate_store.get_release_config()
        return dict(DEFAULT_RELEASE_CONFIG)

    def gate_thresholds() -> dict[str, Any]:
        config = release_config()
        return {key: config.get(key, DEFAULT_RELEASE_CONFIG[key]) for key in GATE_THRESHOLD_KEYS}

    def config_view() -> dict[str, Any]:
        config = release_config()
        view = {key: config.get(key, DEFAULT_RELEASE_CONFIG[key]) for key in RELEASE_CONFIG_KEYS}
        view['updated_at'] = config.get('updated_at')
        return view

    def gate_result(payload: dict[str, Any]) -> dict[str, Any]:
        thresholds = dict(payload.get('thresholds') or {})
        for key, value in gate_thresholds().items():
            thresholds.setdefault(key, value)
        if {'e2ePassRate', 'ragFaithfulness', 'highRiskErrors'} & set(payload):
            checks = {
                'e2ePassRate': float(payload.get('e2ePassRate', 0)) >= float(thresholds['e2ePassRate']),
                'ragFaithfulness': float(payload.get('ragFaithfulness', 0)) >= float(thresholds['ragFaithfulness']),
                'highRiskErrors': int(payload.get('highRiskErrors', int(thresholds['highRiskErrors']) + 1)) <= int(thresholds['highRiskErrors']),
            }
        else:
            checks = {key: bool(value) for key, value in (payload.get('checks') or {}).items()}
        eval_run_id = payload.get('eval_run_id') or payload.get('evalRunId')
        if eval_run_id and evaluation_run_exists:
            checks['evalRunId'] = evaluation_run_exists(str(eval_run_id)) is not None
        return {'passed': bool(checks) and all(checks.values()), 'checks': checks, 'thresholds': thresholds}

    def gate_payload(gate: dict[str, Any]) -> tuple[str | None, str | None]:
        gate_id = str(gate.get('gate_id') or gate.get('gateId') or '') or None
        eval_run_id = gate.get('eval_run_id') or gate.get('evalRunId')
        return gate_id, eval_run_id

    def record(action: str, project: str, name: str, version: str | None, **extra: Any) -> None:
        if not gate_store:
            return
        gate_store.save_record({
            'project': project,
            'name': name,
            'version': version or '',
            'action': action,
            'percentage': extra.get('percentage', 0),
            'gate_id': extra.get('gate_id'),
            'eval_run_id': extra.get('eval_run_id'),
            'detail': extra.get('detail', ''),
            'actor': extra.get('actor') or 'harness-operator',
            'error_rate': extra.get('error_rate'),
            'sample_count': extra.get('sample_count'),
            'threshold': extra.get('threshold'),
        })

    def error_stats(project: str, name: str, version: str | None) -> tuple[float, int]:
        """从技能目录指标里算出该灰度的错误率与样本数。"""
        rows = call("metrics", {}).get("metrics", []) or []
        matched = [row for row in rows
                   if row.get('project') == project and row.get('name') == name
                   and row.get('metric') == 'error_rate'
                   and (not version or str(row.get('version') or '') == str(version))]
        if not matched:
            return 0.0, 0
        values = [float(row.get('value') or 0) for row in matched]
        return sum(values) / len(values), len(values)

    def observe_rollout(project: str, name: str, version: str | None = None) -> dict[str, Any]:
        """观察一次灰度指标：样本不足不处理，超阈值且允许自动回滚时回滚。"""
        rollouts = call("rollouts", {}).get("rollouts", []) or []
        rollout = next((row for row in rollouts
                        if row.get('project') == project and row.get('name') == name
                        and (not version or str(row.get('candidate_version') or '') == str(version))), None)
        if not rollout:
            raise HTTPException(status_code=404, detail=f"灰度发布不存在：{project}/{name}")
        target_version = version or str(rollout.get('candidate_version') or '')
        percentage = int(rollout.get('percentage') or 0)
        config = release_config()
        threshold = float(config.get('rolloutErrorThreshold', DEFAULT_RELEASE_CONFIG['rolloutErrorThreshold']))
        min_samples = int(config.get('rolloutMinSamples', DEFAULT_RELEASE_CONFIG['rolloutMinSamples']))
        auto_rollback = bool(config.get('autoRollback', DEFAULT_RELEASE_CONFIG['autoRollback']))
        error_rate, sample_count = error_stats(project, name, target_version)

        rolled_back = False
        if sample_count < min_samples:
            detail = f"样本不足：{sample_count}/{min_samples}，不触发回滚"
        elif error_rate >= threshold:
            detail = f"错误率 {error_rate} 达到阈值 {threshold}（样本 {sample_count}）"
            if auto_rollback:
                try:
                    call("rollback", {"project": project, "name": name})
                except Exception as exc:
                    detail += f"，回滚失败：{exc}"
                else:
                    rolled_back = True
                    detail += "，已自动回滚"
            else:
                detail += "，未开启自动回滚"
        else:
            detail = f"错误率 {error_rate} 低于阈值 {threshold}（样本 {sample_count}）"

        observation = None
        if gate_store:
            observation = gate_store.save_observation({
                'project': project,
                'name': name,
                'version': target_version,
                'percentage': percentage,
                'error_rate': error_rate,
                'sample_count': sample_count,
                'threshold': threshold,
                'auto_rolled_back': rolled_back,
                'detail': detail,
            })
        if rolled_back:
            record('auto_rollback', project, name, target_version, percentage=0,
                   detail=detail, error_rate=error_rate, sample_count=sample_count, threshold=threshold)
        return {
            'observation': observation,
            'rolledBack': rolled_back,
            'errorRate': error_rate,
            'sampleCount': sample_count,
            'threshold': threshold,
            'minSamples': min_samples,
            'percentage': percentage,
            'version': target_version,
            'detail': detail,
        }

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

    @router.get("/release/records")
    def list_records(limit: int = Query(100, ge=1, le=200)):
        items = gate_store.list_records(limit) if gate_store else []
        if gate_store:
            gates = {gate['gate_id']: gate for gate in gate_store.list_gates(200)}
            for item in items:
                gate = gates.get(item.get('gate_id'))
                if gate:
                    item['checks'] = gate['checks']
                    item['thresholds'] = gate['thresholds']
                    item['eval_run_id'] = item.get('eval_run_id') or gate.get('eval_run_id')
        return {"items": items}

    @router.get("/release/config")
    def get_release_config():
        return {"config": config_view()}

    @router.put("/release/config")
    def save_release_config(payload: ReleaseConfigPayload):
        if not gate_store:
            raise HTTPException(status_code=503, detail='发布治理存储未接入')
        gate_store.save_release_config(payload.model_dump())
        return {"config": config_view()}

    @router.get("/release/gate-thresholds")
    def get_gate_thresholds():
        return {"thresholds": gate_thresholds()}

    @router.put("/release/gate-thresholds")
    def save_gate_thresholds(payload: GateThresholdPayload):
        if not gate_store:
            raise HTTPException(status_code=503, detail='发布治理存储未接入')
        gate_store.save_release_config(payload.model_dump())
        return {"thresholds": gate_thresholds()}

    @router.post("/release/promote")
    def promote(payload: ReleaseActionPayload):
        gate = payload.gate or {}
        stored = None
        if gate_store:
            gate_id, _ = gate_payload(gate)
            if gate_id:
                stored = gate_store.get_gate(gate_id)
        result = gate_result(stored or gate)
        if not gate or not result['passed']:
            raise HTTPException(status_code=412, detail='发布前质量门禁未通过')
        config = release_config()
        response = call("promote", {
            "project": project_value(payload.project),
            "name": payload.name,
            "version": payload.version,
            "percentage": payload.percentage,
            "rolloutErrorThreshold": config.get('rolloutErrorThreshold'),
            "rolloutMinSamples": config.get('rolloutMinSamples'),
            "autoRollback": config.get('autoRollback'),
        })
        gate_id, eval_run_id = gate_payload(gate)
        if stored:
            gate_id = gate_id or stored.get('gate_id')
            eval_run_id = eval_run_id or stored.get('eval_run_id')
        record('promote', project_value(payload.project), payload.name, payload.version,
               percentage=payload.percentage, gate_id=gate_id, eval_run_id=eval_run_id,
               actor=payload.operator, detail=json.dumps(result['checks'], ensure_ascii=False))
        return response

    @router.post("/release/rollouts/advance")
    def advance_rollout(payload: ReleaseRolloutAdvancePayload):
        project = project_value(payload.project)
        current = next((row for row in call("rollouts", {}).get("rollouts", [])
                        if row.get('project') == project and row.get('name') == payload.name), None)
        current_percentage = int((current or {}).get('percentage') or 0)
        if payload.percentage < current_percentage:
            raise HTTPException(status_code=400, detail=f'灰度比例不能低于当前比例 {current_percentage}%')
        version = payload.version or (current or {}).get('candidate_version')
        if not version:
            raise HTTPException(status_code=400, detail='没有可推进的灰度版本')
        config = release_config()
        response = call("promote", {
            "project": project,
            "name": payload.name,
            "version": version,
            "percentage": payload.percentage,
            "rolloutErrorThreshold": config.get('rolloutErrorThreshold'),
            "rolloutMinSamples": config.get('rolloutMinSamples'),
            "autoRollback": config.get('autoRollback'),
        })
        record('advance', project, payload.name, version, percentage=payload.percentage,
               actor=payload.operator,
               detail=f'灰度比例从 {current_percentage}% 推进到 {payload.percentage}%')
        return response

    @router.post("/release/gate")
    def evaluate_gate(payload: ReleaseGatePayload):
        result = gate_result(payload.model_dump())
        if gate_store:
            result['gate'] = gate_store.save_gate({
                'project': project_value(payload.project),
                'name': payload.name,
                'version': payload.version,
                'eval_run_id': payload.evalRunId,
                'passed': result['passed'],
                'checks': result['checks'],
                'thresholds': result['thresholds'],
            })
        return result

    @router.post("/release/rollback")
    def rollback(payload: ReleaseActionPayload):
        response = call("rollback", {"project": project_value(payload.project), "name": payload.name})
        record('rollback', project_value(payload.project), payload.name, payload.version,
               percentage=0, actor=payload.operator, detail='回滚到上一稳定版本')
        return response

    @router.post("/release/rollouts/observe")
    def observe(payload: ReleaseObservePayload):
        return observe_rollout(project_value(payload.project), payload.name, payload.version)

    def observe_active_rollouts() -> None:
        """定时任务：对所有活跃灰度各观察一次，单个失败不影响其它。"""
        rollouts = call("rollouts", {}).get("rollouts", []) or []
        for row in rollouts:
            if not row.get("active"):
                continue
            try:
                observe_rollout(str(row.get("project") or default_project),
                                str(row.get("name") or ""),
                                row.get("candidate_version"))
            except Exception as exc:  # pragma: no cover - 单个灰度失败不影响其它灰度
                logger.warning("灰度观察失败：%s", exc)

    @router.get("/release/observations")
    def list_observations(project: str | None = None, limit: int = Query(100, ge=1, le=200)):
        return {"items": gate_store.list_observations(project, limit) if gate_store else []}

    @router.post("/release/metrics")
    def record_metric(payload: ReleaseMetricPayload):
        response = call("metric", payload.model_dump())
        if response.get('autoRolledBack'):
            project = project_value(payload.project)
            config = release_config()
            threshold = float(config.get('rolloutErrorThreshold', DEFAULT_RELEASE_CONFIG['rolloutErrorThreshold']))
            error_rate, sample_count = error_stats(project, payload.name, payload.version)
            detail = f"错误率触发自动回滚：{payload.metric}={payload.value}"
            record('auto_rollback', project, payload.name, payload.version,
                   percentage=0, detail=detail, error_rate=error_rate,
                   sample_count=sample_count, threshold=threshold)
        return response

    _register_observer(observe_active_rollouts)

    return router
