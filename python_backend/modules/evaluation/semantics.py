"""语义指标模板：内置指标定义与判分输入渲染。

对应规格 S-005。这里只放纯数据与纯函数，不碰模型调用与存储。
"""
from __future__ import annotations

import json
from typing import Any


SEMANTIC_METRICS: dict[str, dict[str, Any]] = {
    "topic_adherence": {
        "label": "话题贴合度",
        "required": ["topics"],
        "instruction": "回答是否始终停留在约定的话题域内，没有跑题、没有扯到无关话题",
    },
    "answer_relevance": {
        "label": "回答相关性",
        "required": [],
        "instruction": "回答是否正面回应了用户的问题，没有答非所问、没有答偏",
    },
    "fact_consistency": {
        "label": "事实一致性",
        "required": ["context"],
        "instruction": "回答是否与给定依据一致，没有出现依据之外或与依据矛盾的事实",
    },
    "trajectory_quality": {
        "label": "轨迹质量",
        "required": [],
        "needs_trace": True,
        "instruction": "执行过程是否走对：必要的步骤有没有漏掉、有没有绕路或做无用动作",
    },
}


def semantic_templates() -> list[dict[str, Any]]:
    """给前端的内置指标模板列表。"""
    return [
        {
            "metric": name,
            "label": item["label"],
            "required": list(item.get("required", [])),
            "instruction": item["instruction"],
        }
        for name, item in SEMANTIC_METRICS.items()
    ]


def _plain(value: Any) -> str:
    if isinstance(value, (list, tuple)):
        return "、".join(str(item) for item in value)
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False)
    return str(value)


def trace_summary(trace: dict[str, Any] | None) -> str:
    """轨迹摘要：工具序列、步骤数、澄清次数、工具调用次数。"""
    trace = trace if isinstance(trace, dict) else {}
    counts = trace.get("counts") or {}
    tools = trace.get("tools") or []
    calls = trace.get("toolCalls") or []
    return (
        f"工具序列: {'、'.join(str(item) for item in tools) or '无'}；"
        f"步骤数: {int(counts.get('step') or 0)}；"
        f"澄清次数: {int(counts.get('clarify') or 0)}；"
        f"工具调用次数: {len(calls)}"
    )


def render_criteria(metric: str, expect: dict[str, Any] | None,
                    trace: dict[str, Any] | None = None) -> str:
    """把指标说明、expect 参数与轨迹摘要渲染成给评委看的 criteria。"""
    item = SEMANTIC_METRICS.get(metric)
    if not item:
        return ""
    parts = [item["instruction"]]
    for key, value in (expect or {}).items():
        parts.append(f"{key}: {_plain(value)}")
    if item.get("needs_trace"):
        parts.append(trace_summary(trace))
    return "；".join(parts)
