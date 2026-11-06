from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from ..domain.execution import ExecutionRequest


class ExecutionQueue(Protocol):
    def enqueue(self, conversation_id: str, agent: str, query: str,
                file_id: str | None) -> dict[str, Any]: ...

    def request_cancel(self, conversation_id: str) -> bool: ...

    def has_live_worker(self) -> bool: ...

    def find_run_by_event(self, conversation_id: str, agent: str, query: str,
                          file_id: str | None, event_id: int) -> dict[str, Any] | None: ...

    def get_run(self, run_id: str) -> dict[str, Any] | None: ...

    def list_runs(self, status: str | None = None, search: str | None = None,
                  limit: int = 100, offset: int = 0) -> tuple[list[dict[str, Any]], int]: ...

    def get_events(self, run_id: str, event_id: int = 0) -> list[dict[str, Any]]: ...

    def request_cancel_run(self, run_id: str) -> bool: ...

    def retry_run(self, run_id: str) -> dict[str, Any] | None: ...


@dataclass(slots=True)
class ExecutionApplicationService:
    """Application use cases for execution; queue storage stays behind a port."""

    queue: ExecutionQueue

    def submit_or_resume(self, request: ExecutionRequest, event_cursor: int = 0) -> dict[str, Any]:
        run = self.queue.find_run_by_event(
            request.conversation_id, request.agent, request.query, request.file_id, event_cursor
        )
        if run:
            return run
        if not self.queue.has_live_worker():
            raise WorkerUnavailableError("Agent Execution Worker 未运行")
        return self.queue.enqueue(request.conversation_id, request.agent, request.query, request.file_id)

    def cancel(self, conversation_id: str) -> bool:
        return self.queue.request_cancel(conversation_id)

    def create(self, request: ExecutionRequest) -> dict[str, Any]:
        if not self.queue.has_live_worker():
            raise WorkerUnavailableError("Agent Execution Worker 未运行")
        return self.queue.enqueue(request.conversation_id, request.agent, request.query, request.file_id)

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        return self.queue.get_run(run_id)

    def list_runs(self, status: str | None = None, search: str | None = None,
                  limit: int = 100, offset: int = 0) -> tuple[list[dict[str, Any]], int]:
        return self.queue.list_runs(status, search, limit, offset)

    def get_events(self, run_id: str, event_id: int = 0) -> list[dict[str, Any]]:
        return self.queue.get_events(run_id, event_id)

    def cancel_run(self, run_id: str) -> bool:
        return self.queue.request_cancel_run(run_id)

    def retry_run(self, run_id: str) -> dict[str, Any] | None:
        if not self.queue.has_live_worker():
            raise WorkerUnavailableError("Agent Execution Worker 未运行")
        return self.queue.retry_run(run_id)


class WorkerUnavailableError(RuntimeError):
    """Raised when execution cannot be accepted because no Worker is alive."""
