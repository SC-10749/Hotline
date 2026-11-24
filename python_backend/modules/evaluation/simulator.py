"""模拟用户：让模型扮演需求方，把对话继续下去。

对应规格 S-003。模拟器只回答「下一句用户说什么」，
返回 END_MARKER 表示诉求已被满足、对话可以结束。
"""
from __future__ import annotations

import json
from typing import Any, Callable

END_MARKER = "__END__"

SYSTEM_PROMPT = (
    "你在扮演一个真实的需求方，正在和助手对话。"
    "只输出你这一句要说的话，不要解释、不要客套、不要重复对方的话。"
    "如果对方已经问清了你要的东西、你的诉求已经被完整满足，只输出 {end}。"
)


def default_user_simulator(profile: str, dialogue: list[dict[str, str]]) -> str:
    """默认实现：走项目已有的模型能力生成下一句用户话术。"""
    from ...config import settings
    from ...llm import build_chat_model
    from langchain_core.messages import HumanMessage, SystemMessage

    model = build_chat_model(settings)
    reply = model.invoke([
        SystemMessage(content=SYSTEM_PROMPT.format(end=END_MARKER)),
        HumanMessage(content=json.dumps({"画像": profile, "对话": dialogue}, ensure_ascii=False)),
    ])
    content = getattr(reply, "content", reply)
    if isinstance(content, list):
        content = "".join(str(block.get("text") or "") if isinstance(block, dict) else str(block)
                          for block in content)
    return str(content or "").strip()


def next_user_message(profile: str, dialogue: list[dict[str, str]],
                      simulator: Callable[[str, list[dict[str, str]]], str] | None = None) -> str:
    """让模拟用户说下一句；返回空串表示对话可以结束。"""
    fn = simulator or default_user_simulator
    try:
        text = str(fn(profile, dialogue) or "").strip()
    except Exception:
        return ""
    return "" if text == END_MARKER else text
