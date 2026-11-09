"""会话人设：机器人角色指令、绑定技能与个人回答风格。

机器人、会话绑定与个人偏好都在本机 data 目录，这里只把跨表数据汇总成
一段可注入模型系统提示词的内容。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .bot_store import BotStore
from .profile_store import ProfileStore


BOT_DB_NAME = 'harness-bots.db'
PROFILE_DB_NAME = 'harness-profile.db'

STYLE_PROMPTS = {
    'concise': '回答保持简洁：先给结论，再列必要要点，不展开冗长推导。',
    'detailed': '回答保持详尽：给出完整推理、依据与适用边界。',
    'friendly': '语气保持亲切自然：先回应对方意图，再给出建议。',
}


def load_persona(data_dir: Path, conversation_id: str) -> dict[str, Any]:
    """读取会话绑定的人设；机器人未启用时只保留个人回答风格。"""
    persona: dict[str, Any] = {'instruction': '', 'skills': [], 'style': ''}
    if not conversation_id:
        return persona
    root = Path(data_dir)
    try:
        bot = BotStore(root / BOT_DB_NAME).session_bot(conversation_id)
    except Exception:
        bot = None
    if bot and bot.get('enabled'):
        persona['instruction'] = str(bot.get('instruction') or '').strip()
        persona['skills'] = [str(value) for value in (bot.get('skills') or [])]
    try:
        profile = ProfileStore(root / PROFILE_DB_NAME).get()
    except Exception:
        profile = {}
    style = str(profile.get('answerStyle') or 'default')
    persona['style'] = STYLE_PROMPTS.get(style, '')
    return persona
