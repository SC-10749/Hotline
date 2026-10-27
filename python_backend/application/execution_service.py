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


class WorkerUnavailableError(RuntimeError):
    """Raised when execution cannot be accepted because no Worker is alive."""
