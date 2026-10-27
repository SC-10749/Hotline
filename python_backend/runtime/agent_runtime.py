from __future__ import annotations

from collections.abc import Iterable
from typing import Protocol


class AgentRuntime(Protocol):
    """Port used by Workers to run an Agent without knowing its internals."""

    def stream(self, agent: str, conversation_id: str, query: str,
               file_id: str | None = None) -> Iterable[dict]: ...


class AgentEngineRuntime:
    """Adapter that exposes the legacy AgentEngine through the runtime port."""

    def __init__(self, engine: object):
        self.engine = engine

    def stream(self, agent: str, conversation_id: str, query: str,
               file_id: str | None = None) -> Iterable[dict]:
        return self.engine.stream(agent, conversation_id, query, file_id)
