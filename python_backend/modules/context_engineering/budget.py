from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from .privacy import sanitize_text


class ContextBudgetExceeded(ValueError):
    def __init__(self):
        super().__init__('当前问题、规则或工具定义超过模型输入预算，请缩小输入范围。')


def token_estimate(value: Any) -> int:
    """UTF-8 byte bound avoids tokenizer downloads and undercounting Chinese text."""
    encoded = json.dumps(value, ensure_ascii=False, separators=(',', ':'), default=str)
    return len(encoded.encode('utf-8')) + 32


def clip_text(text: str, budget: int) -> tuple[str, bool]:
    if token_estimate(text) <= budget:
        return text, False
    marker = '\n[内容已限额，完整原文可按来源读取]'
    available = max(0, budget - token_estimate(marker) - 8)
    return text.encode('utf-8')[:available].decode('utf-8', errors='ignore') + marker, True


@dataclass(frozen=True)
class ContextBudget:
    window: int = 128000
    input_limit: int = 64000
    output_reserve: int = 8192
    safety_margin: int = 2048

    @classmethod
    def from_settings(cls, settings):
        return cls(window=int(getattr(settings, 'context_window', 128000)),
                   input_limit=int(getattr(settings, 'context_input_budget', 64000)),
                   output_reserve=int(getattr(settings, 'context_output_reserve', 8192)),
                   safety_margin=int(getattr(settings, 'context_safety_margin', 2048)))

    @property
    def available(self) -> int:
        values = (self.window, self.input_limit, self.output_reserve, self.safety_margin)
        if min(values) < 0 or not self.output_reserve:
            raise ContextBudgetExceeded()
        return min(self.input_limit, self.window - self.output_reserve - self.safety_margin)

    def check(self, messages, tools=()) -> int:
        size = token_estimate(messages) + token_estimate(list(tools)) + 32 * len(messages)
        if size > self.available:
            raise ContextBudgetExceeded()
        return size


def assemble_context(system: str, query: str, history: list, sections: list[dict],
                     budget: ContextBudget, tools=()) -> tuple[list[dict], dict]:
    system = sanitize_text(system)
    query = sanitize_text(query)
    messages = [{'role': 'system', 'content': system}, {'role': 'user', 'content': query}]
    budget.check(messages, tools)
    manifest = []
    # Reserve space for intact recent turns before adding lower-priority evidence.
    history_limit = max(0, (budget.available - budget.check(messages, tools)) // 3)
    turns = []
    history_size = 0
    for row in reversed(history):
        pair = [{'role': 'user', 'content': sanitize_text(row.question)},
                {'role': 'assistant', 'content': sanitize_text(row.answer or '')}]
        size = token_estimate(pair) + 64
        if history_size + size > history_limit:
            break
        turns.insert(0, pair)
        history_size += size
    for pair in turns:
        messages[-1:-1] = pair
    for section in sections:
        text = sanitize_text(section.get('content', ''))
        if not text:
            continue
        remaining = budget.available - budget.check(messages, tools) - 256
        allocation = min(int(section.get('budget', 8000)), remaining)
        if allocation < 256:
            manifest.append({'source': section['source'], 'omitted': True})
            continue
        content, truncated = clip_text(text, allocation)
        # JSON quoting preserves boundaries around untrusted retrieved material.
        block = json.dumps({'contextSource': section['source'], 'data': content}, ensure_ascii=False)
        candidate = messages[:-1] + [{'role': 'user', 'content': block}] + messages[-1:]
        try:
            budget.check(candidate, tools)
        except ContextBudgetExceeded:
            manifest.append({'source': section['source'], 'omitted': True})
            continue
        messages = candidate
        manifest.append({'source': section['source'], 'truncated': truncated,
                         'estimatedTokens': token_estimate(content)})
    estimated = budget.check(messages, tools)
    return messages, {'estimatedTokens': estimated, 'inputBudget': budget.available,
                      'outputReserve': budget.output_reserve, 'tokenMethod': 'utf8-byte-upper-bound',
                      'sections': manifest, 'historyIds': [str(row.id) for row in history[-len(turns):]] if turns else [],
                      'omittedHistoryTurns': len(history) - len(turns)}
