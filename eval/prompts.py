"""提示词版本表：评测台的核心。

一个变体 = 系统提示 + 用户提示模板 + 说明。
`current` 必须与 python_backend/agents.py 的 _fallback 完全一致，
其余变体是待比较的候选。

改这里的 prompt 后，fingerprint 会变；采样时记下 fingerprint，
分数掉的时候先看指纹变没变，就能分清是 prompt 改了还是模型/检索变了。
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass


@dataclass(frozen=True)
class PromptVariant:
    name: str
    system: str
    user: str
    description: str = ""

    def fingerprint(self) -> str:
        payload = f"{self.system}\x00{self.user}".encode("utf-8")
        return hashlib.sha256(payload).hexdigest()[:12]


# user 模板里的占位符：{route} {context} {query}
VARIANTS: dict[str, PromptVariant] = {
    "current": PromptVariant(
        name="current",
        system="你是 Hotline Agent，请用中文给出准确、结构清晰的回答。",
        user="本次选择的召回链路：{route}\n请基于以下知识库内容回答问题：\n{context}\n\n问题：{query}",
        description="线上现状，与 agents._fallback 对齐，作为对照基线",
    ),
    "cited": PromptVariant(
        name="cited",
        system=(
            "你是 Hotline Agent，请用中文给出准确、结构清晰的回答。"
            "凡是从知识库得出的结论，必须在句末标注来源片段编号，例如 [片段2]。"
            "如果知识库内容不足以回答，直接说明“文档中没有相关信息”，不要推测。"
        ),
        user="本次选择的召回链路：{route}\n知识库内容（按编号引用）：\n{context}\n\n问题：{query}",
        description="要求逐句标注来源、不足时明确拒答；用于验证“引用”和“拒答”这两条提示词约束是否生效",
    ),
}


def get(name: str) -> PromptVariant:
    if name not in VARIANTS:
        raise SystemExit(f"未知提示词变体：{name}，可选：{', '.join(VARIANTS)}")
    return VARIANTS[name]


def render(variant: PromptVariant, query: str, contexts: list[str], route: str) -> list[dict[str, str]]:
    """把召回片段编号后填进模板，返回 OpenAI 格式的 messages。"""
    if contexts:
        context = "\n\n".join(f"[片段{i}]\n{text}" for i, text in enumerate(contexts, start=1))
    else:
        context = "（没有召回到任何内容）"
    return [
        {"role": "system", "content": variant.system},
        {"role": "user", "content": variant.user.format(route=route, context=context, query=query)},
    ]
