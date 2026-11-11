from __future__ import annotations

import hashlib
import json
import os
import platform
import signal
import threading
import time
from collections.abc import Iterable
from uuid import uuid4

from ..bootstrap import load_environment

load_environment()

from python_backend.modules.execution.engine import AgentEngine, TaskManager  # noqa: E402
from ..config import settings  # noqa: E402
from python_backend.modules.documents.service import DocumentService  # noqa: E402
from python_backend.modules.storage.objects import ObjectStorage  # noqa: E402
from python_backend.modules.documents.ppt import generate_ppt  # noqa: E402
from python_backend.modules.skills.registry import SkillRegistry  # noqa: E402
from python_backend.modules.storage.relational import Storage  # noqa: E402
from python_backend.modules.retrieval.vector_store import PgVectorStore  # noqa: E402
from ..infrastructure.queue import SqliteExecutionQueue  # noqa: E402
from ..infrastructure.settings_store import SettingsStore  # noqa: E402
from ..infrastructure.resource_store import ResourceStore  # noqa: E402
from ..runtime import AgentEngineRuntime, AgentRuntime  # noqa: E402
from ..modules.workspaces.context import load_workspace_rules, recall_workspace
from ..modules.retrieval.workspace_index import WorkspaceIndex
from ..modules.artifacts.store import ArtifactStore, artifact_metadata  # noqa: E402
from ..modules.execution.tools import set_current_run_id, set_tool_policy  # noqa: E402
from ..infrastructure.persona import load_persona  # noqa: E402


class ExecutionWorker:
    def __init__(
        self,
        store: SqliteExecutionQueue,
        runtime: AgentRuntime,
        tasks: TaskManager,
        object_store: ObjectStorage,
        poll_interval: float = 0.5,
        artifacts: ArtifactStore | None = None,
        policy: dict | None = None,
    ):
        self.store = store
        self.runtime = runtime
        self.tasks = tasks
        self.object_store = object_store
        self.poll_interval = poll_interval
        self.artifacts = artifacts
        # Harness 设置是运行时默认值来源：超时与重试次数在这里真正生效。
        self.timeout_seconds = int((policy or {}).get('defaultTimeoutSeconds') or 0)
        self.retry_count = int((policy or {}).get('defaultRetryCount') or 0)
        self.isolation = str((policy or {}).get('isolation') or '')
        self.capacity = 1
        self.token_budget = int((policy or {}).get('defaultTokenBudget') or 0)
        self._token_usage: dict[str, int] = {}
        self.runtime_version = f"1.0.0 · py{platform.python_version()}"
        self._retry_attempts: dict[str, int] = {}
        self.worker_id = f"{os.getpid()}-{uuid4().hex[:8]}"
        self._shutdown = threading.Event()

    def _agent_policy(self, run: dict[str, Any]) -> dict[str, Any]:
        """按运行关联的 Agent 定义装配工具权限、Skill 绑定与模型路由。"""
        agent_id = str(run.get('agent_id') or '').strip()
        if not agent_id:
            return {}
        data_dir = self.object_store.settings.data_dir
        try:
            agent = ResourceStore(data_dir / 'harness-resources.db').get_agent(agent_id)
        except Exception:
            return {}
        if not agent:
            return {}

        def _names(value: Any) -> list[str]:
            if isinstance(value, list):
                return [str(item) for item in value if str(item)]
            if isinstance(value, str) and value.strip():
                try:
                    parsed = json.loads(value)
                except Exception:
                    return []
                if isinstance(parsed, list):
                    return [str(item) for item in parsed if str(item)]
            return []

        policy: dict[str, Any] = {
            'agentId': agent_id,
            'name': agent.get('name', ''),
            'version': agent.get('version', ''),
            'enabled': bool(agent.get('enabled')),
            'tools': _names(agent.get('tools')),
            'skills': _names(agent.get('skills')),
            'model': agent.get('model', ''),
        }
        model_name = str(policy.get('model') or '').strip()
        if model_name:
            try:
                from ..infrastructure.registry_store import RegistryStore
                models = RegistryStore(data_dir / 'harness-registry.db').list_models()
                matched = next((item for item in models
                                if str(item.get('model_id')) == model_name
                                or str(item.get('name')) == model_name), None)
                if matched:
                    policy['modelRoute'] = {
                        'modelId': matched.get('model_id'),
                        'provider': matched.get('provider'),
                        'route': matched.get('route'),
                        'fallbackModelId': matched.get('fallback_model_id'),
                    }
            except Exception:
                pass
        return policy

    def _heartbeat(self, current_run_id: str | None) -> None:
        self.store.heartbeat_worker(self.worker_id, os.getpid(), current_run_id,
                                    capacity=self.capacity, runtime_version=self.runtime_version)

    def _monitor_run(self, run_id: str, conversation_id: str, stopped: threading.Event) -> None:
        deadline = time.monotonic() + self.timeout_seconds if self.timeout_seconds > 0 else None
        while not stopped.wait(3):
            self._heartbeat(run_id)
            self.store.heartbeat_run(run_id, self.worker_id)
            if self.store.is_cancel_requested(run_id):
                self.tasks.stop(conversation_id)
                return
            if deadline is not None and time.monotonic() >= deadline:
                # 超时按失败结束，避免运行无限占用 Worker。
                self.store.append_event(run_id, {"type": "error", "content": f"运行超过 {self.timeout_seconds} 秒默认超时，已终止"})
                self.store.finish(run_id, "failed", "timeout")
                self.tasks.stop(conversation_id)
                return

    def _events_for_run(self, run: dict) -> Iterable[dict]:
        agent = run["agent"]
        conversation_id = run["conversation_id"]
        query = run["query"]
        file_id = run["file_id"]
        events = (self.runtime.stream_run(run) if isinstance(self.runtime, AgentEngineRuntime)
                  else self.runtime.stream(agent, conversation_id, query, file_id))
        if agent != "ppt":
            yield from events
            return

        terminal = None
        for event in events:
            if event.get('type') in {'complete', 'error'}:
                terminal = event
                break
            yield event
        if not terminal or terminal['type'] != 'complete':
            if terminal:
                yield terminal
            return
        if self.store.is_cancel_requested(run['run_id']):
            yield {'type': 'error', 'content': '任务已停止'}
            return
        if self.artifacts is None:
            raise RuntimeError('产物登记服务未配置')
        root = self.object_store.settings.generated_dir
        started = time.monotonic()
        yield {'type': 'step', 'stage': 'ppt_generate', 'content': '正在生成演示文稿', 'status': 'running'}
        output = generate_ppt(query, root / run['run_id'])
        yield {'type': 'step', 'stage': 'ppt_generate', 'content': '演示文稿已生成', 'status': 'completed',
               'durationMs': int((time.monotonic() - started) * 1000),
               'details': {'file': output.name}}
        content = output.read_bytes()
        content_type = 'application/vnd.openxmlformats-officedocument.presentationml.presentation'
        backend = self.object_store.backend
        key = output.relative_to(root).as_posix() if backend == 'local' else f"ppt/{run['run_id']}/{output.name}"
        if backend == 'minio':
            self.object_store.upload_bytes(content, key, content_type)
        artifact = self.artifacts.register(run_id=run['run_id'], name=output.name, size=len(content),
                                           sha256=hashlib.sha256(content).hexdigest(), content_type=content_type,
                                           storage_backend=backend, storage_key=key)
        if backend == 'minio':
            output.unlink(missing_ok=True)
        metadata = artifact_metadata(artifact)
        yield {'type': 'artifact', 'content': '已生成演示文稿', 'artifact': metadata}
        if self.store.is_cancel_requested(run['run_id']):
            yield {'type': 'error', 'content': '任务已停止'}
            return
        yield {'type': 'text', 'content': f"\n下载文件: {metadata['download']}"}
        yield terminal

    def run_once(self) -> bool:
        run = self.store.claim_next(self.worker_id)
        if not run:
            return False

        run_id = run["run_id"]
        conversation_id = run["conversation_id"]
        # 登记运行上下文，工具侧的审批请求据此关联到本次运行。
        set_current_run_id(run_id)
        self._heartbeat(run_id)
        if self.isolation:
            # 记录本次运行实际使用的运行时策略，便于在运行详情里核对设置是否生效。
            self.store.append_event(run_id, {
                "type": "policy",
                "content": "运行时策略",
                "policy": {
                    "isolation": self.isolation,
                    "timeoutSeconds": self.timeout_seconds,
                    "retryCount": self.retry_count,
                    "tokenBudget": self.token_budget,
                },
            })
        agent_policy = self._agent_policy(run)
        if agent_policy:
            tools_blocked = not agent_policy.get('enabled')
            set_tool_policy(allowed=None if tools_blocked else (agent_policy.get('tools') or None),
                            blocked=tools_blocked)
            self.store.append_event(run_id, {
                "type": "policy",
                "content": "Agent 装配",
                "policy": {
                    "agentId": agent_policy.get('agentId'),
                    "name": agent_policy.get('name'),
                    "version": agent_policy.get('version'),
                    "enabled": agent_policy.get('enabled'),
                    "tools": agent_policy.get('tools'),
                    "toolsBlocked": tools_blocked,
                    "skills": agent_policy.get('skills'),
                    "skillBindingRecorded": agent_policy.get('skills') or [],
                    "model": agent_policy.get('model'),
                    "modelRoute": agent_policy.get('modelRoute'),
                },
            })
        else:
            set_tool_policy(allowed=None, blocked=False)
        if self.store.is_cancel_requested(run_id):
            self.store.append_event(run_id, {"type": "error", "content": "任务已停止"})
            self.store.finish(run_id, "cancelled")
            self._heartbeat(None)
            return True

        stopped = threading.Event()
        monitor = threading.Thread(
            target=self._monitor_run, args=(run_id, conversation_id, stopped), daemon=True
        )
        monitor.start()
        terminal_event = None
        try:
            for event in self._events_for_run(run):
                usage = event.get("usage")
                if isinstance(usage, dict) and usage.get("totalTokens"):
                    total = self._token_usage.get(run_id, 0) + int(usage.get("totalTokens") or 0)
                    self._token_usage[run_id] = total
                    self.store.append_event(run_id, {**event, "usage": {**usage, "runTotal": total,
                                                                        "budget": self.token_budget}})
                    if self.token_budget > 0 and total > self.token_budget:
                        self.store.append_event(run_id, {"type": "error",
                                                        "content": f"运行超出 token 预算 {self.token_budget}"})
                        self.store.finish(run_id, "failed", "token budget exceeded")
                        terminal_event = {"type": "error", "content": "token budget exceeded"}
                        break
                    continue
                self.store.append_event(run_id, event)
                if event.get("type") in {"complete", "error"}:
                    terminal_event = event
                    break

            if terminal_event and terminal_event.get("type") == "complete":
                self.store.finish(run_id, "completed")
            elif terminal_event and terminal_event.get("type") == "error":
                cancelled = self.store.is_cancel_requested(run_id)
                self.store.finish(
                    run_id,
                    "cancelled" if cancelled else "failed",
                    None if cancelled else str(terminal_event.get("content", "")),
                )
            elif self.store.is_cancel_requested(run_id):
                self.store.append_event(run_id, {"type": "error", "content": "任务已停止"})
                self.store.finish(run_id, "cancelled")
            else:
                self.store.append_event(run_id, {"type": "error", "content": "任务未正常结束"})
                self.store.finish(run_id, "failed", "execution ended without terminal event")
        except Exception as exc:
            self.store.append_event(run_id, {
                "type": "error",
                "content": "任务执行失败，请检查 Worker 日志后重试。",
            })
            self.store.finish(run_id, "failed", type(exc).__name__)
            print(f"Execution run {run_id} failed ({type(exc).__name__}).", flush=True)
        finally:
            stopped.set()
            monitor.join(timeout=1)
            self.tasks.remove(conversation_id)
            set_current_run_id(None)
            set_tool_policy(allowed=None, blocked=False)
            self._heartbeat(None)
        if self.retry_count > 0 and self._failed_run(run_id):
            self._schedule_retry(run_id, conversation_id)
        return True

    def _failed_run(self, run_id: str) -> bool:
        run = self.store.get_run(run_id)
        return bool(run and run.get("status") == "failed")

    def _schedule_retry(self, run_id: str, conversation_id: str) -> None:
        attempts = self._retry_attempts.get(conversation_id, 0)
        if attempts >= self.retry_count:
            return
        try:
            retried = self.store.retry_run(run_id)
        except Exception:
            return
        if not retried:
            return
        self._retry_attempts[conversation_id] = attempts + 1
        self.store.append_event(run_id, {
            "type": "retry",
            "content": f"已按默认重试次数创建重试运行 {retried['run_id']}",
            "retryRunId": retried["run_id"],
        })

    def run_forever(self) -> None:
        if isinstance(self.runtime, AgentEngineRuntime):
            self.runtime.start()
        self._heartbeat(None)
        print(f"Execution Worker {self.worker_id} started.", flush=True)
        last_heartbeat = time.monotonic()
        try:
            while not self._shutdown.is_set():
                if time.monotonic() - last_heartbeat >= 5:
                    self._heartbeat(None)
                    last_heartbeat = time.monotonic()
                if not self.run_once():
                    self._shutdown.wait(self.poll_interval)
        finally:
            self.store.remove_worker(self.worker_id)
            if isinstance(self.runtime, AgentEngineRuntime):
                self.runtime.close()

    def stop(self) -> None:
        self._shutdown.set()


def build_worker() -> ExecutionWorker:
    settings.ensure_dirs()
    storage = Storage(settings)
    tasks = TaskManager(settings)
    vector_store = PgVectorStore(settings)
    object_store = ObjectStorage(settings)
    skills = SkillRegistry(settings)
    documents = DocumentService(settings, storage, object_store, vector_store)
    resources = ResourceStore(settings.data_dir / 'harness-resources.db')
    workspace_index = WorkspaceIndex(settings.data_dir / 'workspace-index.db')
    engine = AgentEngine(settings, storage, tasks, vector_store, skills, documents,
                          persona_reader=lambda conversation_id: load_persona(settings.data_dir, conversation_id),
                          workspace_rules_reader=lambda workspace_id: load_workspace_rules(resources, workspace_id),
                          workspace_recall=lambda workspace_id, query, source_id='': recall_workspace(
                              resources, storage, workspace_index, vector_store,
                              vector_store.embed_batch, workspace_id, query, source_id),
                          workspace_source_reader=workspace_index.read_source)
    harness_settings = SettingsStore(settings.data_dir / 'harness-settings.db').get()
    return ExecutionWorker(
        SqliteExecutionQueue(settings.execution_db_path), AgentEngineRuntime(engine), tasks, object_store,
        artifacts=ArtifactStore(settings.data_dir / 'artifacts.db'),
        policy=harness_settings,
    )


def main() -> None:
    worker = build_worker()
    signal.signal(signal.SIGINT, lambda *_: worker.stop())
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, lambda *_: worker.stop())
    worker.run_forever()


if __name__ == "__main__":
    main()

