from __future__ import annotations

import threading
import time
from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass, field

from langchain.agents import create_agent
from langchain.agents.middleware import AgentMiddleware
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.tools import BaseTool
from langsmith import tracing_context

from .trace import trace_preview
from ..context_engineering.snapshots import context_snapshot
from ..context_engineering.budget import ContextBudget, ContextBudgetExceeded, clip_text
from ..context_engineering.privacy import sanitize_text, sanitize_value


@dataclass(frozen=True)
class AgentEvent:
    type: str
    content: str = ''
    details: dict = field(default_factory=dict)


class _ExecutionStopped(Exception):
    pass


class _ExecutionGuard(AgentMiddleware):
    def __init__(self, is_stopped: Callable[[], bool], budget=None, archive_tool=None,
                 history_policy='current-question-only'):
        self.is_stopped = is_stopped
        self.budget = budget or ContextBudget()
        self.archive_tool = archive_tool
        self.history_policy = history_policy
        self._lock = threading.Lock()
        self._model_calls = 0
        self._tool_calls = 0
        self._tool_chars = 0
        self._call_ids: set[str] = set()
        self._archive_refs: dict[str, str] = {}

    def check_stop(self):
        if self.is_stopped():
            raise _ExecutionStopped()

    def wrap_model_call(self, request, handler):
        self.check_stop()
        with self._lock:
            if self._model_calls >= 8:
                raise ValueError('model call budget')
            self._model_calls += 1
            call_index = self._model_calls
        safe_messages = []
        for message in request.messages:
            updates = {'content': sanitize_value(message.content)}
            if isinstance(message, AIMessage) and message.tool_calls:
                updates['tool_calls'] = [{**call, 'args': sanitize_value(call['args'])} for call in message.tool_calls]
            safe_messages.append(message.model_copy(update=updates))
        system = request.system_message
        if system:
            system = system.model_copy(update={'content': sanitize_value(system.content)})
        definitions = []
        safe_tools = []
        for tool in request.tools:
            if isinstance(tool, dict):
                definitions.append(sanitize_value(tool))
                safe_tools.append(sanitize_value(tool))
            else:
                safe_tools.append(tool.model_copy(update={'description': sanitize_text(tool.description)}))
                definitions.append({'type': 'function', 'function': {'name': tool.name,
                    'description': sanitize_text(tool.description),
                    'parameters': sanitize_value(tool.get_input_schema().model_json_schema())}})
        def check():
            values = ([system] if system else []) + safe_messages
            return self.budget.check([item.model_dump() for item in values], definitions)
        try:
            check()
        except ContextBudgetExceeded:
            # Replace complete old tool cycles together, preserving tool_call_id pairing.
            index = 0
            while index < len(safe_messages):
                message = safe_messages[index]
                if not isinstance(message, AIMessage) or not message.tool_calls:
                    index += 1
                    continue
                ids = {call['id'] for call in message.tool_calls}
                end = index + 1
                found = set()
                while end < len(safe_messages) and isinstance(safe_messages[end], ToolMessage):
                    found.add(safe_messages[end].tool_call_id)
                    end += 1
                if ids != found or end == len(safe_messages):
                    index = end
                    continue
                refs = [self._archive_refs.get(identity, 'tool:' + identity) for identity in sorted(ids)]
                safe_messages[index:end] = [HumanMessage(content='已归档的工具交互，完整结果来源 ' + ', '.join(refs))]
                try:
                    check()
                    break
                except ContextBudgetExceeded:
                    index += 1
        estimated = check()
        request = request.override(messages=safe_messages, system_message=system, tools=safe_tools,
                                   model_settings={**(request.model_settings or {}), 'max_tokens': self.budget.output_reserve})
        messages = ([system] if system else []) + safe_messages
        started = time.monotonic()
        request.runtime.stream_writer(AgentEvent('step', '正在分析任务并选择工具', {
            'stage': 'planning', 'status': 'running',
        }))
        snapshot = context_snapshot('skill-model', messages, tools=request.tools,
                                    model_name=getattr(request.model, 'model_name', request.model._llm_type),
                                    sources={'modelCall': call_index, 'historyPolicy': self.history_policy,
                                             'estimatedTokens': estimated, 'inputBudget': self.budget.available,
                                             'tokenMethod': 'utf8-byte-upper-bound'})
        request.runtime.stream_writer(AgentEvent(snapshot['type'], snapshot['content'], {'snapshot': snapshot['snapshot']}))
        result = handler(request)
        self.check_stop()
        input_tokens = 0
        output_tokens = 0
        total_tokens = 0
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
            meta = getattr(message, 'usage_metadata', None)
            if isinstance(meta, dict) and meta:
                input_tokens = max(input_tokens, int(meta.get('input_tokens') or 0))
                output_tokens = max(output_tokens, int(meta.get('output_tokens') or 0))
                total_tokens = max(total_tokens, int(meta.get('total_tokens') or 0)
                                   or (input_tokens + output_tokens))
        request.runtime.stream_writer(AgentEvent('step', '任务分析完成', {
            'stage': 'planning', 'status': 'completed',
            'durationMs': round((time.monotonic() - started) * 1000),
        }))
        if total_tokens:
            request.runtime.stream_writer(AgentEvent('usage', '模型用量', {
                'inputTokens': input_tokens, 'outputTokens': output_tokens, 'totalTokens': total_tokens,
            }))
        return result

    def wrap_tool_call(self, request, handler):
        self.check_stop()
        with self._lock:
            if self._tool_calls >= 16:
                raise ValueError('tool call budget')
            self._tool_calls += 1
        identity = {'toolCallId': request.tool_call['id'], 'toolName': request.tool_call['name']}
        writer = request.runtime.stream_writer
        arguments, truncated = trace_preview(sanitize_value(request.tool_call.get('args', {})), 4000)
        started = time.monotonic()
        writer(AgentEvent('tool_start', '开始调用工具', {
            **identity, 'arguments': arguments, 'argumentsTruncated': truncated, 'status': 'running',
        }))
        try:
            result = handler(request)
            self.check_stop()
            if not isinstance(result, ToolMessage):
                raise ValueError('unsupported tool response')
            source = self.archive_tool(result) if self.archive_tool else ''
            if source:
                self._archive_refs[result.tool_call_id] = source
            safe_content = sanitize_text(str(result.content))
            safe_content, clipped = clip_text(safe_content, min(12000, max(512, self.budget.available // 4)))
            if clipped and source:
                safe_content += '\n完整工具结果来源 ' + source
            result = result.model_copy(update={'content': safe_content})
            with self._lock:
                self._tool_chars += len(str(result.content))
            output, truncated = trace_preview(result.content, 12000)
            truncated = truncated or clipped
            failed = result.status == 'error' or (isinstance(output, dict) and bool(output.get('error')))
        except Exception as exc:
            cancelled = isinstance(exc, _ExecutionStopped)
            writer(AgentEvent('tool_end', '工具调用已停止' if cancelled else '工具调用失败，请检查工具配置或执行预算', {
                **identity, 'status': 'cancelled' if cancelled else 'failed',
                'durationMs': round((time.monotonic() - started) * 1000),
            }))
            raise
        writer(AgentEvent('tool_end', '工具返回错误' if failed else '工具调用完成', {
            **identity, 'status': 'failed' if failed else 'completed', 'output': output,
            'outputTruncated': truncated, 'durationMs': round((time.monotonic() - started) * 1000),
        }))
        return result


def run_agent(model: BaseChatModel, system_prompt: str, query: str,
              tools: Sequence[BaseTool], is_stopped: Callable[[], bool], *, initial_messages=None,
              budget=None, archive_tool=None) -> Iterator[AgentEvent]:
    guard = _ExecutionGuard(is_stopped, budget, archive_tool,
                            'task-history-and-memory' if initial_messages is not None else 'current-question-only')
    try:
        with tracing_context(enabled=False):
            guard.check_stop()
            agent = create_agent(model=model, tools=list(tools), system_prompt=system_prompt, middleware=[guard])
            answer = ''
            for mode, update in agent.stream({'messages': initial_messages if initial_messages is not None
                                              else [{'role': 'user', 'content': query}]},
                                             config={'recursion_limit': 64}, stream_mode=['updates', 'custom']):
                if mode == 'custom':
                    if isinstance(update, AgentEvent):
                        yield update
                    continue
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
