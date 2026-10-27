from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class ExecutionStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass(frozen=True, slots=True)
class ExecutionRequest:
    """Validated business input for one Agent execution."""

    conversation_id: str
    agent: str
    query: str
    file_id: str | None = None

    def __post_init__(self) -> None:
        if not self.conversation_id:
            raise ValueError("conversationId 不能为空")
        if not self.query:
            raise ValueError("查询参数不能为空")
        if self.agent == "file" and not self.file_id:
            raise ValueError("fileId 不能为空")
