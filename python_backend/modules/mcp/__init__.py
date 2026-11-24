"""最小 stdio 型 MCP 连接器。

支持 initialize 探测、tools/list 工具发现和 tools/call 工具调用，
三者复用同一套进程启动与收尾逻辑，不引入 MCP SDK。
"""

from __future__ import annotations

import json
import os
import queue
import subprocess
import threading
import time
from typing import Any

PROBE_TIMEOUT_SECONDS = 10.0
LIST_TIMEOUT_SECONDS = 10.0
CALL_TIMEOUT_SECONDS = 30.0
PROTOCOL_VERSION = '2024-11-05'


class McpError(Exception):
    """MCP 交互失败；消息里不包含命令、参数、本机路径或环境变量。"""


def _initialize_params() -> dict[str, Any]:
    return {
        'protocolVersion': PROTOCOL_VERSION,
        'capabilities': {},
        'clientInfo': {'name': 'harness-agent', 'version': '1.0'},
    }


def _normalize_config(config: Any) -> tuple[str, list[str], dict[str, str]]:
    if not isinstance(config, dict):
        raise McpError('MCP 配置格式不正确')
    command = config.get('command')
    if not isinstance(command, str) or not command.strip():
        raise McpError('MCP 配置缺少 command')
    args = config.get('args') or []
    if not isinstance(args, list) or any(not isinstance(item, str) for item in args):
        raise McpError('MCP 配置的 args 必须是字符串数组')
    env_patch = config.get('env') or {}
    if not isinstance(env_patch, dict):
        raise McpError('MCP 配置的 env 必须是对象')
    env = {**os.environ, **{str(key): str(value) for key, value in env_patch.items()}}
    return command, list(args), env


class _StdioSession:
    """一次 stdio 会话：进程启动、请求发送、按 id 匹配响应、进程收尾。"""

    def __init__(self, config: Any):
        self.command, self.args, self.env = _normalize_config(config)
        self.process: subprocess.Popen | None = None
        self._lines: queue.Queue[Any] = queue.Queue()
        self._counter = 0

    def __enter__(self) -> '_StdioSession':
        try:
            self.process = subprocess.Popen(
                [self.command, *self.args],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                env=self.env,
                text=True,
                encoding='utf-8',
                bufsize=1,
            )
        except Exception:
            raise McpError('无法启动 MCP 服务器') from None
        threading.Thread(target=self._pump, daemon=True).start()
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()

    def _pump(self) -> None:
        try:
            for line in self.process.stdout:
                self._lines.put(line)
        except Exception:
            pass
        finally:
            self._lines.put(None)

    def call(self, method: str, params: Any = None, timeout: float = PROBE_TIMEOUT_SECONDS) -> Any:
        """发送一次 JSON-RPC 请求，按 id 匹配响应；服务端可先发通知或多条消息。"""
        self._counter += 1
        request_id = self._counter
        request: dict[str, Any] = {'jsonrpc': '2.0', 'id': request_id, 'method': method}
        if params is not None:
            request['params'] = params
        try:
            self.process.stdin.write(json.dumps(request) + '\n')
            self.process.stdin.flush()
        except Exception:
            raise McpError('无法启动 MCP 服务器') from None
        deadline = time.monotonic() + timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise McpError(f'MCP 服务器在 {int(timeout)} 秒内没有响应')
            try:
                line = self._lines.get(timeout=remaining)
            except queue.Empty:
                raise McpError(f'MCP 服务器在 {int(timeout)} 秒内没有响应')
            if line is None:
                raise McpError('MCP 服务器没有返回响应')
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                raise McpError('MCP 服务器返回的不是合法 JSON-RPC 响应') from None
            if not isinstance(payload, dict) or payload.get('jsonrpc') != '2.0':
                raise McpError('MCP 服务器返回的不是 JSON-RPC 响应')
            if payload.get('id') != request_id:
                continue  # 通知或无关 id 的消息，继续等本请求的响应
            if payload.get('error'):
                raise McpError(f'MCP 服务器拒绝了 {method} 请求')
            return payload.get('result')

    def close(self) -> None:
        if self.process is not None:
            _terminate(self.process)


def probe_stdio_server(config: Any, timeout: float = PROBE_TIMEOUT_SECONDS) -> dict[str, Any]:
    """对 stdio 型 MCP 服务器做一次 initialize 探测。

    返回 {'ok': bool, 'message': str, 'details': dict}；
    任何异常都转成 ok=False，消息里不包含命令、参数或本机路径。
    """
    try:
        with _StdioSession(config) as session:
            result = session.call('initialize', _initialize_params(), timeout=timeout)
    except McpError as exc:
        return {'ok': False, 'message': str(exc)}
    except Exception:
        return {'ok': False, 'message': '无法启动 MCP 服务器'}
    return {'ok': True, 'message': '连接正常', 'details': _describe(result)}


def list_stdio_tools(config: Any, timeout: float = LIST_TIMEOUT_SECONDS) -> dict[str, Any]:
    """发现 MCP 服务器提供的工具清单。"""
    try:
        with _StdioSession(config) as session:
            session.call('initialize', _initialize_params(), timeout=timeout)
            result = session.call('tools/list', {}, timeout=timeout)
    except McpError as exc:
        return {'ok': False, 'message': str(exc), 'tools': []}
    except Exception:
        return {'ok': False, 'message': '无法启动 MCP 服务器', 'tools': []}
    tools: list[dict[str, Any]] = []
    if isinstance(result, dict):
        for item in result.get('tools') or []:
            if isinstance(item, dict) and isinstance(item.get('name'), str):
                tools.append({'name': item['name'],
                              'description': item.get('description') or '',
                              'inputSchema': item.get('inputSchema') or {}})
    return {'ok': True, 'message': f'发现 {len(tools)} 个工具', 'tools': tools}


def call_stdio_tool(config: Any, tool_name: str, arguments: Any,
                    timeout: float = CALL_TIMEOUT_SECONDS) -> dict[str, Any]:
    """调用 MCP 服务器上的一个工具，返回 {'ok', 'content', 'isError', 'message'}。"""
    if not isinstance(tool_name, str) or not tool_name.strip():
        return {'ok': False, 'message': '工具名称不能为空', 'content': None, 'isError': False}
    if arguments is None:
        arguments = {}
    if not isinstance(arguments, dict):
        return {'ok': False, 'message': '工具参数必须是 JSON 对象', 'content': None, 'isError': False}
    try:
        with _StdioSession(config) as session:
            session.call('initialize', _initialize_params(), timeout=timeout)
            result = session.call('tools/call', {'name': tool_name, 'arguments': arguments}, timeout=timeout)
    except McpError as exc:
        return {'ok': False, 'message': str(exc), 'content': None, 'isError': False}
    except Exception:
        return {'ok': False, 'message': '无法启动 MCP 服务器', 'content': None, 'isError': False}
    if not isinstance(result, dict):
        return {'ok': False, 'message': 'MCP 服务器返回的不是 JSON-RPC 响应', 'content': None, 'isError': False}
    is_error = bool(result.get('isError'))
    content = result.get('content')
    if content is None:
        content = []
    elif not isinstance(content, list):
        content = [content]
    return {'ok': not is_error,
            'message': '调用成功' if not is_error else '工具返回错误',
            'content': content,
            'isError': is_error}


def _describe(result: Any) -> dict[str, Any]:
    details: dict[str, Any] = {}
    if isinstance(result, dict):
        version = result.get('protocolVersion')
        if isinstance(version, str):
            details['protocolVersion'] = version
        server_info = result.get('serverInfo')
        if isinstance(server_info, dict) and isinstance(server_info.get('name'), str):
            details['serverName'] = server_info['name']
    return details


def _terminate(process: subprocess.Popen) -> None:
    """结束探测进程，避免留下残留进程。

    先结束进程再关管道：读线程正阻塞在 readline 时关闭管道会卡住。
    """
    try:
        process.terminate()
        process.wait(timeout=2)
    except Exception:
        try:
            process.kill()
            process.wait(timeout=2)
        except Exception:
            pass
    for stream in (process.stdin, process.stdout):
        try:
            if stream is not None:
                stream.close()
        except Exception:
            pass
