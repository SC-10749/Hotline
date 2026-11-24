"""Agent as Tool：把 bot 包装成可被调用的工具。

机器人定义在 harness_bot（角色指令 + 绑定技能），登记在 harness_tool：source='agent'，
input_schema.agent.bot_id 指向机器人，input_schema 里另附工具入参（与 MCP 把连接配置
放在 input_schema.mcp 里同一套路）。调用时按登记项找到机器人，注入人设跑一次对话，
结果按 MCP 工具结果的结构返回：状态 + 摘要 + 澄清方向。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable, Protocol

from langchain_core.tools import BaseTool, StructuredTool
from pydantic import BaseModel, Field, StrictStr

from ...infrastructure.bot_store import BotStore
from ...infrastructure.persona import BOT_DB_NAME
from ...infrastructure.registry_store import RegistryStore
from .tools import REGISTRY_DB_NAME, prepare_tool_call

# 登记来源：机器人作为工具。
AGENT_SOURCE = 'agent'
# 回给调用方的正文上限，超出截断；工具结果预算还有一层裁剪。
MAX_SUMMARY_CHARS = 4000
# 登记状态里表示不可用的取值。
DISABLED_STATUS = {'disabled', 'stopped', 'offline', 'error'}


class AgentToolInput(BaseModel):
    """Agent 工具入参：交给该智能体处理的一次请求。"""

    query: StrictStr = Field(min_length=1, max_length=20000,
                             description='要交给该智能体处理的原始问题')
    clarification: StrictStr = Field(default='', max_length=8000,
                                     description='用户对上一轮澄清的回答；为空表示首次提问')


class AgentRunner(Protocol):
    """执行器：用机器人人设跑一次对话，返回结构化结果。"""

    def __call__(self, persona: dict[str, Any], query: str, clarification: str) -> dict[str, Any]: ...


def bot_persona(bot: dict[str, Any]) -> dict[str, Any]:
    """机器人定义 → 会话人设。"""
    return {'instruction': str(bot.get('instruction') or '').strip(),
            'skills': [str(item) for item in (bot.get('skills') or [])],
            'style': ''}


def agent_bot_id(row: dict[str, Any]) -> str:
    """登记项指向的机器人编号。"""
    schema = row.get('input_schema')
    agent = schema.get('agent') if isinstance(schema, dict) else None
    return str(agent.get('bot_id') or '').strip() if isinstance(agent, dict) else ''


def agent_rows(registry: RegistryStore) -> list[dict[str, Any]]:
    """登记为 agent 来源、且状态可用的登记项。"""
    try:
        rows = registry.list_tools()
    except (OSError, ValueError):
        return []
    return [row for row in rows
            if str(row.get('source') or '').strip() == AGENT_SOURCE
            and str(row.get('status') or '').strip().lower() not in DISABLED_STATUS]


def build_agent_tools(registry: RegistryStore, bots: BotStore,
                      runner: Callable[..., dict[str, Any]]) -> list[BaseTool]:
    """按登记项生成可调用的智能体工具。"""
    tools: list[BaseTool] = []
    for row in agent_rows(registry):
        bot_id = agent_bot_id(row)
        bot = bots.get(bot_id) if bot_id else None
        if not bot or not bot.get('enabled'):
            continue
        tools.append(_build_tool(row, bot, runner, registry.path))
    return tools


def agent_tools_from_dir(data_dir: Path,
                         runner: Callable[..., dict[str, Any]]) -> list[BaseTool]:
    """从运行数据目录读登记与机器人，生成可调用工具。"""
    root = Path(data_dir)
    try:
        registry = RegistryStore(root / REGISTRY_DB_NAME)
        bots = BotStore(root / BOT_DB_NAME)
    except Exception:
        return []
    return build_agent_tools(registry, bots, runner)


def _build_tool(row: dict[str, Any], bot: dict[str, Any],
                runner: Callable[..., dict[str, Any]], registry_path: Path) -> BaseTool:
    name = str(row.get('name') or '').strip()
    persona = bot_persona(bot)

    def call_agent(query: str, clarification: str = '') -> str:
        arguments = {'query': query, 'clarification': clarification}
        prepare_tool_call(name, arguments, registry_db=registry_path)
        return json.dumps(runner(persona, query, clarification), ensure_ascii=False)

    description = str(row.get('description') or '').strip()
    return StructuredTool.from_function(
        func=call_agent,
        name=name,
        description=description or f'调用「{bot.get("name") or name}」智能体处理问题。',
        args_schema=AgentToolInput,
        handle_validation_error='参数无效，请提供要交给该智能体处理的问题。',
    )


def collect_events(generator: Any) -> tuple[list[dict[str, Any]], Any]:
    """消费事件生成器，返回事件列表与生成器的返回值。"""
    events: list[dict[str, Any]] = []
    while True:
        try:
            events.append(next(generator))
        except StopIteration as stop:
            return events, stop.value
