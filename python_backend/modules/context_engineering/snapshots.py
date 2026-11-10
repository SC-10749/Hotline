from __future__ import annotations

from datetime import datetime, timezone

from ..execution.trace import trace_preview


def context_snapshot(stage: str, messages: list, *, model_name: str = '',
                     model_configured: bool = True, sources: dict | None = None, tools=()) -> dict:
    """Capture a detached preview of prepared inputs, never provider credentials."""
    budget_source = (sources or {}).get('context') or sources or {}
    budget = {key: budget_source[key] for key in ('estimatedTokens', 'inputBudget', 'outputReserve')
              if isinstance(budget_source.get(key), int)}
    previews = []
    for message in messages[:24]:
        if isinstance(message, dict):
            role, content = message.get('role', 'unknown'), message.get('content', '')
            extra = {key: message[key] for key in ('tool_calls', 'tool_call_id') if key in message}
        else:
            role, content = message.type, message.content
            extra = {}
            if getattr(message, 'tool_calls', None):
                extra['tool_calls'] = message.tool_calls
            if getattr(message, 'tool_call_id', None):
                extra['tool_call_id'] = message.tool_call_id
        content, truncated = trace_preview(content, 6000)
        protocol, protocol_truncated = trace_preview(extra, 4000)
        previews.append({'role': {'human': 'user', 'ai': 'assistant'}.get(role, role),
                         'content': content, 'truncated': truncated,
                         'toolProtocol': protocol, 'toolProtocolTruncated': protocol_truncated})
    tool_previews = []
    for tool in list(tools)[:8]:
        if isinstance(tool, dict):
            tool = tool.get('function', tool)
            definition = {key: tool.get(key) for key in ('name', 'description', 'parameters')}
        else:
            definition = {'name': tool.name, 'description': tool.description,
                          'parameters': tool.get_input_schema().model_json_schema()}
        definition, truncated = trace_preview(definition, 12000)
        tool_previews.append({'definition': definition, 'truncated': truncated})
    sources, sources_truncated = trace_preview(sources or {}, 4000)
    model_name, _ = trace_preview(model_name, 256)
    return {'type': 'context_snapshot', 'content': '已捕获调用前上下文预览', 'snapshot': {
        'schemaVersion': 1, 'capturedAt': datetime.now(timezone.utc).isoformat(), 'stage': stage, 'modelName': model_name,
        'modelConfigured': model_configured, 'messageCount': len(messages), 'messages': previews, 'budget': budget,
        'omittedMessages': max(0, len(messages) - 24), 'tools': tool_previews,
        'omittedTools': max(0, len(tools) - 8), 'sources': sources, 'sourcesTruncated': sources_truncated,
    }}
