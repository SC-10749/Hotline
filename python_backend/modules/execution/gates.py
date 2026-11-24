"""意图与需求门闸：置信度不足或需求说不清时先向用户澄清。"""
from __future__ import annotations

from typing import Any

from python_backend.llm import model_ready
from python_backend.models import SessionMessage
from python_backend.modules.context_engineering.privacy import sanitize_text
from python_backend.modules.execution.constants import (REQUIREMENT_BRIEF_CHARS, REQUIREMENT_FLAG,
                                                        REQUIREMENT_SKILL, TDD_RECOMMENDATION)
from python_backend.modules.intent import (ACTION_CATALOG, ClarifyRequest, build_clarify_request,
                                           build_requirement_clarify_request, classify)


class GateMixin:
    @staticmethod
    def _is_tdd_handoff(query: str) -> bool:
        """这条请求是不是「把需求交给 TDD 技能」的交接口令。"""
        text = (query or '').strip()
        return text == TDD_RECOMMENDATION or text.startswith(TDD_RECOMMENDATION)

    def _requirement_brief(self, history) -> str:
        """交接内容：最近一次需求分析助手产出的需求条目。"""
        for row in reversed(list(history or [])):
            thinking = str(getattr(row, 'thinking', '') or '')
            if REQUIREMENT_FLAG not in thinking:
                continue
            answer = str(getattr(row, 'answer', '') or '').strip()
            if answer:
                return answer[:REQUIREMENT_BRIEF_CHARS]
        return ''

    def _requirement_mode(self, persona: dict[str, Any] | None) -> bool:
        """机器人绑定了需求分析技能时，走需求分析流程而不是通用意图门闸。"""
        if not persona or not self.skills:
            return False
        for skill_id in persona.get('skills') or []:
            skill = self.skills.get(skill_id)
            if skill and skill.name == REQUIREMENT_SKILL:
                return True
        return False

    def _requirement_gate(self, agent: str, query: str, file_id: str | None,
                          history: list[SessionMessage] | None,
                          clarified: bool) -> ClarifyRequest | None:
        """需求级门闸：需求本身说不清时先给三个理解方向，说得清就放行。

        上一轮刚澄清过时不再拦：用户正在回答澄清问题，再拦一次就是同一件事追两遍。
        """
        if agent not in {'chat', 'deep'} or file_id or clarified:
            return None
        if not model_ready(self.settings):
            return None
        context = '\n'.join(f'用户：{row.question}\n助手：{row.answer}'
                            for row in (history or [])[-2:])
        return build_requirement_clarify_request(sanitize_text(query), self.model.chat, context)

    def _intent_gate(self, agent: str, query: str, file_id: str | None) -> tuple[ClarifyRequest, tuple[str, ...]] | None:
        """门闸：意图不够确定时，返回一次需求澄清；确定时返回 None。

        文件问答、PPT 生成和技能执行按各自入口处理。
        澄清回复仍进入分类级联，后续判定采用当前用户输入。
        """
        if agent not in {"chat", "deep"} or file_id:
            return None
        if not model_ready(self.settings):
            return None
        catalog = ACTION_CATALOG
        # 候选由 classify 内部合并（关键词 + 向量），这里不再重复召回。
        # 决策层可用时它同时给出意图和歧义度，比大模型自报把握程度准。
        result = classify(query, catalog, self.model.chat, gate=self.INTENT_GATE,
                          decision=self.decision.judge if self.decision.config.usable else None)
        if not result.gated:
            return None
        request = build_clarify_request(query, catalog, result.candidates, self.model.chat)
        return request, result.candidates
