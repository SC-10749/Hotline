from __future__ import annotations

import os
import signal
import threading
import time
from collections.abc import Iterable
from uuid import uuid4

from ..bootstrap import load_environment

load_environment()

from ..agents import AgentEngine, TaskManager  # noqa: E402
from ..config import settings  # noqa: E402
from ..documents import DocumentService  # noqa: E402
from ..object_store import ObjectStorage  # noqa: E402
from ..ppt import generate_ppt  # noqa: E402
from ..skills import SkillRegistry  # noqa: E402
from ..storage import Storage  # noqa: E402
from ..vector_store import PgVectorStore  # noqa: E402
from ..infrastructure.queue import SqliteExecutionQueue  # noqa: E402
from ..runtime import AgentEngineRuntime, AgentRuntime  # noqa: E402


class ExecutionWorker:
    def __init__(
        self,
        store: SqliteExecutionQueue,
        runtime: AgentRuntime,
        tasks: TaskManager,
        object_store: ObjectStorage,
        poll_interval: float = 0.5,
    ):
        self.store = store
        self.runtime = runtime
        self.tasks = tasks
        self.object_store = object_store
        self.poll_interval = poll_interval
        self.worker_id = f"{os.getpid()}-{uuid4().hex[:8]}"
        self._shutdown = threading.Event()

    def _monitor_run(self, run_id: str, conversation_id: str, stopped: threading.Event) -> None:
        while not stopped.wait(3):
            self.store.heartbeat_worker(self.worker_id, os.getpid(), run_id)
            self.store.heartbeat_run(run_id, self.worker_id)
            if self.store.is_cancel_requested(run_id):
                self.tasks.stop(conversation_id)

    def _events_for_run(self, run: dict) -> Iterable[dict]:
        agent = run["agent"]
        conversation_id = run["conversation_id"]
        query = run["query"]
        file_id = run["file_id"]
        if agent != "ppt":
            return self.runtime.stream(agent, conversation_id, query, file_id)

        output = generate_ppt(query, settings.generated_dir)
        events = list(self.runtime.stream(agent, conversation_id, query, file_id))
        ppt_url = self.object_store.upload_bytes(
            output.read_bytes(),
            f"ppt/{conversation_id}/{output.name}",
            "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        )
        download_url = ppt_url if settings.file_storage_backend == "minio" else f"/generated/{output.name}"
        events.insert(-1, {"type": "text", "content": f"\n下载文件: {download_url}"})
        if settings.file_storage_backend == "minio":
            output.unlink(missing_ok=True)
        return events

    def run_once(self) -> bool:
        run = self.store.claim_next(self.worker_id)
        if not run:
            return False

        run_id = run["run_id"]
        conversation_id = run["conversation_id"]
        self.store.heartbeat_worker(self.worker_id, os.getpid(), run_id)
        if self.store.is_cancel_requested(run_id):
            self.store.append_event(run_id, {"type": "error", "content": "任务已停止"})
            self.store.finish(run_id, "cancelled")
            self.store.heartbeat_worker(self.worker_id, os.getpid(), None)
            return True

        stopped = threading.Event()
        monitor = threading.Thread(
            target=self._monitor_run, args=(run_id, conversation_id, stopped), daemon=True
        )
        monitor.start()
        terminal_event = None
        try:
            for event in self._events_for_run(run):
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
            self.store.heartbeat_worker(self.worker_id, os.getpid(), None)
        return True

    def run_forever(self) -> None:
        self.store.heartbeat_worker(self.worker_id, os.getpid(), None)
        print(f"Execution Worker {self.worker_id} started.", flush=True)
        last_heartbeat = time.monotonic()
        try:
            while not self._shutdown.is_set():
                if time.monotonic() - last_heartbeat >= 5:
                    self.store.heartbeat_worker(self.worker_id, os.getpid(), None)
                    last_heartbeat = time.monotonic()
                if not self.run_once():
                    self._shutdown.wait(self.poll_interval)
        finally:
            self.store.remove_worker(self.worker_id)

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
    engine = AgentEngine(settings, storage, tasks, vector_store, skills, documents)
    return ExecutionWorker(
        SqliteExecutionQueue(settings.execution_db_path), AgentEngineRuntime(engine), tasks, object_store
    )


def main() -> None:
    worker = build_worker()
    signal.signal(signal.SIGINT, lambda *_: worker.stop())
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, lambda *_: worker.stop())
    worker.run_forever()


if __name__ == "__main__":
    main()

