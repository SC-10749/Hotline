"""技能交接的共享口径：推荐项指向哪个技能，旧数据怎么升级。

引擎产出推荐项、模型层序列化历史推荐项都从这里取文案，避免两处各写一份。
"""

from __future__ import annotations

import json
from typing import Any

# 需求条目产出完整后给出的下一步建议：交给 TDD 落地。
TDD_RECOMMENDATION = '按 TDD 把这些需求写成测试'
# 交接给哪个技能：推荐项带上技能名，前端据此切到技能助手，不再靠字面量对齐。
TDD_SKILL = 'hotline-tdd'


def normalize_recommendations(values: list[Any]) -> list[Any]:
    """把旧数据里的字符串推荐项升级成结构化项。

    旧会话存的是纯字符串，前端拿不到技能名，点它切不到技能助手；
    已升级的项原样保留，其余字符串不动。
    """
    items: list[Any] = []
    for value in values or []:
        if isinstance(value, dict):
            items.append(value)
        elif value == TDD_RECOMMENDATION:
            items.append({'label': TDD_RECOMMENDATION, 'skill': TDD_SKILL})
        else:
            items.append(value)
    return items


def normalize_recommendations_json(raw: str | None) -> str | None:
    """序列化层的升级入口：读不出列表就原样返回，不改坏历史数据。"""
    if not raw:
        return raw
    try:
        values = json.loads(raw)
    except (TypeError, ValueError):
        return raw
    if not isinstance(values, list):
        return raw
    return json.dumps(normalize_recommendations(values), ensure_ascii=False)
