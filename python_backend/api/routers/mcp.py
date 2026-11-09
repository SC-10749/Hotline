"""MCP 服务器工具发现与工具调用。

与 api/routers/registry.py 分开：registry 只登记连接配置，本路由负责真正
发现工具清单和发起工具调用。响应里不回显命令、参数、本机路径或环境变量。
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ...infrastructure.registry_store import RegistryStore
from ...modules.execution.tools import validate_tool_arguments
from ...modules.mcp import call_stdio_tool, list_stdio_tools

DISCOVERY_TIMEOUT_SECONDS = 5.0


class ToolCallPayload(BaseModel):
    arguments: dict[str, Any] = Field(default_factory=dict)


def _mcp_config(tool: dict[str, Any]) -> dict[str, Any] | None:
    schema = tool.get('input_schema') or {}
    config = schema.get('mcp') if isinstance(schema, dict) else None
    return config if isinstance(config, dict) else None


def create_mcp_router(store: RegistryStore) -> APIRouter:
    router = APIRouter()

    @router.get('/harness/mcp/servers')
    def list_mcp_servers():
        items = []
        for server in store.list_mcp_servers():
            tool = store.get_tool(server['tool_id']) or {}
            config = _mcp_config(tool)
            if config:
                probe = list_stdio_tools(config, timeout=DISCOVERY_TIMEOUT_SECONDS)
            else:
                probe = {'ok': False, 'message': '缺少 MCP 连接配置', 'tools': []}
            items.append({**server,
                          'tools': [item['name'] for item in probe.get('tools', [])],
                          'message': '' if probe.get('ok') else probe.get('message', '')})
        return {'items': items}

    @router.post('/harness/mcp/servers/{tool_id}/tools/{tool_name}/call')
    def call_mcp_tool(tool_id: str, tool_name: str, payload: ToolCallPayload):
        tool = store.get_tool(tool_id)
        if not tool:
            raise HTTPException(status_code=404, detail='MCP 服务器不存在')
        config = _mcp_config(tool)
        if not config:
            raise HTTPException(status_code=404, detail='该工具不是 MCP 服务器')
        discovery = list_stdio_tools(config)
        if not discovery.get('ok'):
            raise HTTPException(status_code=502, detail=discovery.get('message') or 'MCP 服务器不可用')
        matched = next((item for item in discovery.get('tools', []) if item['name'] == tool_name), None)
        if matched is None:
            raise HTTPException(status_code=404, detail='工具不存在')
        try:
            validate_tool_arguments(matched.get('inputSchema') or {}, payload.arguments)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        result = call_stdio_tool(config, tool_name, payload.arguments)
        return {'ok': result['ok'], 'content': result.get('content'),
                'isError': result.get('isError', False), 'message': result.get('message', '')}

    return router
