"""System One 决策客户端：一次前向给出意图与歧义度，不生成文本。

阿里云百炼的 decision-model-preview 与 TypeSafe 的 Jev 用同一套协议（state +
typed questions → choice/noul/score 答案），只有端点不同。因此这个客户端既能接
百炼，也能把 base_url 换成 Jev 的官方端点而不改调用方。

相对大模型自报把握程度，这里问的是「用户这句话有多含糊」——这是训练过的判断，
实测比让模型自己打分准得多：含糊提问的歧义度稳定在 0.82 以上，说清楚了的多在 0.6 以下。
"""

from __future__ import annotations

import json
import urllib.request
from dataclasses import dataclass

from .catalog import IntentCatalog

# 歧义度达到该值即认为需要先澄清再执行。
# 实测（29 条清晰 + 18 条含糊）：阈值 0.86 时含糊提问召回 17/18、清晰提问误判 1/29。
AMBIGUITY_GATE = 0.86

_AMBIGUOUS_INSTRUCTION = "用户的诉求是否存在多种合理解释，需要先向用户澄清才能确定？"


@dataclass(frozen=True)
class DecisionConfig:
    """决策模型接口参数。"""

    base_url: str
    api_key: str
    model: str = "decision-model-preview"
    timeout: float = 30.0

    @property
    def usable(self) -> bool:
        return bool(self.base_url and self.api_key and self.model)


@dataclass(frozen=True)
class DecisionResult:
    """一次决策的结论：意图、该意图的把握程度、以及用户诉求的歧义度。"""

    intent: str
    confidence: float
    ambiguity: float


def build_questions(catalog: IntentCatalog) -> dict[str, dict]:
    """把意图目录编成 System One 的 typed questions。

    choice 的每项要带上示例，否则模型分不清近似的意图（比如 file 与 chat）。
    """
    criteria: dict[str, str] = {}
    for item in catalog.intents:
        text = item.description
        if item.examples:
            text += " 例如：" + "；".join(item.examples)
        criteria[item.name] = text
    return {
        "intent": {
            "type": "choice",
            "instructions": "判断用户这句话的核心诉求属于哪一类",
            "criteria": criteria,
        },
        "ambiguous": {
            "type": "noul",
            "instructions": _AMBIGUOUS_INSTRUCTION,
        },
    }


def parse_decision(payload: dict, catalog: IntentCatalog) -> DecisionResult | None:
    """解析 System One 响应；结构不对或意图不在目录内时返回 None。"""
    if not isinstance(payload, dict):
        return None
    answers = payload.get("answers")
    if not isinstance(answers, dict):
        return None
    intent_answer = answers.get("intent")
    if not isinstance(intent_answer, dict):
        return None
    name = catalog.resolve(str(intent_answer.get("choice") or ""))
    if not name:
        return None
    confidence = _number(intent_answer.get("confidence"))
    ambiguous_answer = answers.get("ambiguous")
    ambiguity = _number(ambiguous_answer.get("noul")) if isinstance(ambiguous_answer, dict) else 0.0
    return DecisionResult(name, confidence, ambiguity)


def _number(value) -> float:
    """把上游数值收进 0~1；不是数字就当 0。"""
    try:
        return max(0.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        return 0.0


class DecisionClient:
    """System One 决策模型的最小客户端。"""

    def __init__(self, config: DecisionConfig):
        self.config = config

    def judge(self, query: str, catalog: IntentCatalog) -> DecisionResult | None:
        """问一次模型拿意图与歧义度；未配置或调用失败时返回 None。"""
        if not self.config.usable or not query.strip():
            return None
        payload = json.dumps({
            "model": self.config.model,
            "state": query[:2000],
            "questions": build_questions(catalog),
        }, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(
            self.config.base_url.rstrip("/") + "/systemone",
            data=payload,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.config.api_key}",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=self.config.timeout) as response:
                body = json.loads(response.read().decode("utf-8"))
        except Exception:
            return None
        return parse_decision(body, catalog)


def decision_config_from_settings(settings) -> DecisionConfig:
    """从应用配置读出决策模型接口参数。

    未配置时不启用决策层，级联照旧走大模型判定。
    """
    return DecisionConfig(
        base_url=str(getattr(settings, 'decision_base_url', '') or ''),
        api_key=str(getattr(settings, 'decision_api_key', '') or ''),
        model=str(getattr(settings, 'decision_model', '') or 'decision-model-preview'),
    )
