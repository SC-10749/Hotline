from __future__ import annotations

import threading
from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass

from langchain.agents import create_agent
from langchain.agents.middleware import AgentMiddleware
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.tools import BaseTool
from langsmith import tracing_context


@dataclass(frozen=True)
class AgentEvent:
    type: str
    content: str = ''


class _ExecutionStopped(Exception):
    pass


class _ExecutionGuard(AgentMiddleware):
    def __init__(self, is_stopped: Callable[[], bool]):
        self.is_stopped = is_stopped
        self._lock = threading.Lock()
        self._model_calls = 0
        self._tool_calls = 0
        self._tool_chars = 0
        self._call_ids: set[str] = set()

    def check_stop(self):
        if self.is_stopped():
            raise _ExecutionStopped()

    def wrap_model_call(self, request, handler):
        self.check_stop()
        with self._lock:
            if self._model_calls >= 8:
                raise ValueError('model call budget')
            self._model_calls += 1
        result = handler(request)
        self.check_stop()
        for message in result.result:
            if not isinstance(message, AIMessage):
                continue
            if message.invalid_tool_calls:
                raise ValueError('invalid tool protocol')
            for call in message.tool_calls:
                identity = call.get('id')
                if not identity or identity in self._call_ids:
                    raise ValueError('invalid tool call id')
                self._call_ids.add(identity)
        return result

    def wrap_tool_call(self, request, handler):
        self.check_stop()
        with self._lock:
            if self._tool_calls >= 16:
                raise ValueError('tool call budget')
            self._tool_calls += 1
        result = handler(request)
        self.check_stop()
        if not isinstance(result, ToolMessage):
            raise ValueError('unsupported tool response')
        with self._lock:
            self._tool_chars += len(str(result.content))
            if self._tool_chars > 64000:
                raise ValueError('tool output budget')
        return result


def run_agent(model: BaseChatModel, system_prompt: str, query: str,
              tools: Sequence[BaseTool], is_stopped: Callable[[], bool]) -> Iterator[AgentEvent]:
    guard = _ExecutionGuard(is_stopped)
    try:
        with tracing_context(enabled=False):
            guard.check_stop()
            agent = create_agent(model=model, tools=list(tools), system_prompt=system_prompt, middleware=[guard])
            answer = ''
            for update in agent.stream({'messages': [{'role': 'user', 'content': query}]},
                                       config={'recursion_limit': 64}, stream_mode='updates'):
                guard.check_stop()
                for state in update.values():
                    if not isinstance(state, dict):
                        continue
                    for message in state.get('messages', []):
                        if isinstance(message, AIMessage) and not message.tool_calls:
                            answer = message.text
            guard.check_stop()
            if not answer:
                raise ValueError('empty model answer')
            yield AgentEvent('text', answer)
            yield AgentEvent('done')
    except _ExecutionStopped:
        yield AgentEvent('error', '任务已停止')
    except Exception:
        yield AgentEvent('error', '模型或工具调用失败，或已达到执行预算；请检查模型工具调用支持与配置后重试。')
