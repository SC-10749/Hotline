from __future__ import annotations

from collections.abc import Iterable
from typing import Protocol

from ..modules.execution.parallel import task_key_for


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

    def stream_run(self, run: dict) -> Iterable[dict]:
        slot = str(run.get('slot') or '')
        # 子任务（slot 非空）用独立任务键与独立历史，普通对话语义不变。
        task_key = task_key_for(run['conversation_id'], slot)
        return self.engine.stream(run['agent'], run['conversation_id'], run['query'], run['file_id'],
                                  workspace_id=run.get('workspace_id', ''), run_id=run['run_id'],
                                  workspace_root=run.get('workspace_root', ''),
                                  task_key=task_key, persist_history=not slot)

    def start(self):
        if self.engine.context:
            self.engine.context.start()

    def close(self):
        if self.engine.context:
            self.engine.context.close()
