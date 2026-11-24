"""Evaluation capability: rule based scoring plus optional model scoring.

规则评分不消耗模型额度；只有 rubric 明确写成 {"type": "model"} 或 {"type": "semantic"} 时才会调用模型，
模型不可用时如实记为 scorer_unavailable，不伪造分数。
"""
from __future__ import annotations

import json
import re
from typing import Any, Callable


__all__ = ["score_case", "score_with_model", "model_scorer_unavailable"]

MODEL_RUBRIC_TYPE = "model"
TRACE_RUBRIC_TYPE = "trace"
MULTI_RUBRIC_TYPE = "multi"
SEMANTIC_RUBRIC_TYPE = "semantic"
MAX_RULE_DEPTH = 5
_FENCE = re.compile(r"```(?:json)?s*(.*?)```", re.S)


def _text(value: Any) -> str:
    return value if isinstance(value, str) else str(value)


def model_scorer_unavailable(reason: str) -> dict[str, Any]:
    """模型评分不可用时的统一结果：分数记 0，verdict 记 scorer_unavailable。"""
    return {"score": 0.0, "verdict": "scorer_unavailable", "detail": f"模型评分不可用：{reason}"}


def _prompt_payload(rubric: dict[str, Any], actual_output: str, expected_output: str) -> dict[str, Any]:
    """给评委模型的统一提问结构。"""
    return {
        "task": "判断实际输出是否满足期望输出与评分要求",
        "requirement": rubric.get("prompt") or "",
        "criteria": rubric.get("criteria") or "",
        "expected": expected_output,
        "actual": actual_output,
        "output_format": '{"score": 0到1的分数, "verdict": "passed 或 failed", "reason": "判定理由"}',
    }


def _invoke_model(model: Any, rubric: dict[str, Any], actual_output: str, expected_output: str) -> Any:
    """把评分提问发给指定模型，返回模型原始输出。"""
    from langchain_core.messages import HumanMessage

    prompt = _prompt_payload(rubric, actual_output, expected_output)
    reply = model.invoke([HumanMessage(content=json.dumps(prompt, ensure_ascii=False))])
    content = getattr(reply, "content", reply)
    if isinstance(content, list):
        # 部分网关返回分块内容，这里拼成纯文本再解析。
        content = "".join(str(block.get("text") or "") if isinstance(block, dict) else str(block)
                          for block in content)
    return content


def _default_model_scorer(rubric: dict[str, Any], actual_output: str, expected_output: str) -> Any:
    """走项目已有的模型能力做一次结构化评分，返回模型原始输出。"""
    from ...config import settings
    from ...llm import build_chat_model

    model = build_chat_model(settings)
    return _invoke_model(model, rubric, actual_output, expected_output)


def _resolve_judge(judge_model_id: str) -> dict[str, Any] | None:
    """解析判分评委：返回 {name, scorer}；模型 id 不存在时返回 None，不静默换默认评委。"""
    from ...config import settings
    from ...llm import build_chat_model, build_chat_model_by_id, model_config

    if judge_model_id:
        from ...llm import find_registered_model

        row = find_registered_model(settings, judge_model_id)
        if not row:
            return None
        name = str(row.get("name") or judge_model_id)

        def scorer(rubric: dict[str, Any], actual_output: str, expected_output: str) -> Any:
            model = build_chat_model_by_id(settings, judge_model_id)
            return _invoke_model(model, rubric, actual_output, expected_output)

        return {"name": name, "scorer": scorer}

    name = str(model_config(settings).get("model") or "默认模型")

    def scorer(rubric: dict[str, Any], actual_output: str, expected_output: str) -> Any:
        model = build_chat_model(settings)
        return _invoke_model(model, rubric, actual_output, expected_output)

    return {"name": name, "scorer": scorer}


def _parse_model_reply(raw: Any) -> dict[str, Any] | None:
    """解析模型返回的 JSON 评分结果；无法解析返回 None。"""
    if isinstance(raw, dict):
        data = raw
    else:
        text = _text(raw or "").strip()
        fenced = _FENCE.search(text)
        if fenced:
            text = fenced.group(1).strip()
        start = text.find("{")
        end = text.rfind("}")
        if start < 0 or end <= start:
            return None
        try:
            data = json.loads(text[start:end + 1])
        except (TypeError, ValueError):
            return None
    if not isinstance(data, dict) or "score" not in data:
        return None
    try:
        score = float(data["score"])
    except (TypeError, ValueError):
        return None
    score = max(0.0, min(1.0, score))
    verdict = _text(data.get("verdict") or "").strip().lower()
    if verdict not in {"passed", "failed"}:
        verdict = "passed" if score >= 0.5 else "failed"
    reason = _text(data.get("reason") or "").strip()
    return {"score": score, "verdict": verdict, "detail": reason or "模型评分"}


def score_with_model(rubric: dict[str, Any] | None, actual_output: str,
                     expected_output: str = "",
                     model_scorer: Callable[[dict[str, Any], str, str], Any] | None = None) -> dict[str, Any]:
    """用模型给一个样本打分；模型不可用时返回 scorer_unavailable。"""
    rules = rubric if isinstance(rubric, dict) else {}
    scorer = model_scorer or _default_model_scorer
    try:
        raw = scorer(rules, actual_output or "", expected_output or "")
    except Exception as exc:
        return model_scorer_unavailable(f"{type(exc).__name__}: {exc}")
    parsed = _parse_model_reply(raw)
    if parsed is None:
        return model_scorer_unavailable("模型返回不是合法的 JSON 评分结果")
    return parsed


def score_case(actual_output: str, expected_output: str = "",
               rubric: dict[str, Any] | None = None,
               model_scorer: Callable[[dict[str, Any], str, str], Any] | None = None,
               trace: dict[str, Any] | None = None,
               judge_resolver: Callable[[str], dict[str, Any] | None] | None = None) -> dict[str, Any]:
    """Score one sample and return {score, verdict, detail}."""
    return _score(actual_output, expected_output, rubric, model_scorer, trace, judge_resolver, 0)


def _score(actual_output: str, expected_output: str,
           rubric: dict[str, Any] | None,
           model_scorer: Callable[[dict[str, Any], str, str], Any] | None,
           trace: dict[str, Any] | None,
           judge_resolver: Callable[[str], dict[str, Any] | None] | None,
           depth: int) -> dict[str, Any]:
    output = actual_output or ""
    expected = expected_output or ""
    rules = rubric if isinstance(rubric, dict) else {}
    kind = str(rules.get("type") or "").strip()

    if kind == MODEL_RUBRIC_TYPE:
        return score_with_model(rules, output, expected, model_scorer)

    if kind == SEMANTIC_RUBRIC_TYPE:
        return _score_semantic(rules, output, expected, trace, model_scorer, judge_resolver)

    if kind == TRACE_RUBRIC_TYPE:
        from .analysis import score_trace
        return score_trace(rules.get("expect"), trace)

    if kind == MULTI_RUBRIC_TYPE:
        return _score_multi(rules, output, expected, model_scorer, trace, judge_resolver, depth)

    if not kind:
        if not expected.strip():
            return {"score": 0.0, "verdict": "not_scored", "detail": "样本没有期望输出和评分规则，未评分"}
        passed = expected in output
        return {
            "score": 1.0 if passed else 0.0,
            "verdict": "passed" if passed else "failed",
            "detail": "实际输出包含期望输出" if passed else "实际输出不包含期望输出",
        }

    if kind == "always":
        return {"score": 1.0, "verdict": "passed", "detail": "规则 always：直接判定通过"}

    if kind not in {"contains", "equals", "json_equals"}:
        return {"score": 0.0, "verdict": "invalid_rubric", "detail": f"未知的评分规则类型：{kind}"}

    if "value" not in rules:
        return {"score": 0.0, "verdict": "invalid_rubric", "detail": f"评分规则 {kind} 缺少 value"}

    value = rules["value"]
    if kind == "contains":
        passed = _text(value) in output
        detail = f"实际输出包含 {value}" if passed else f"实际输出不包含 {value}"
    elif kind == "equals":
        passed = output.strip() == _text(value).strip()
        detail = "实际输出与期望完全一致" if passed else "实际输出与期望不一致"
    else:
        try:
            left = json.loads(output)
        except (TypeError, ValueError):
            left = None
            left_ok = False
        else:
            left_ok = True
        try:
            right = json.loads(value) if isinstance(value, str) else json.loads(json.dumps(value, ensure_ascii=False))
        except (TypeError, ValueError):
            right = None
            right_ok = False
        else:
            right_ok = True
        if left_ok and right_ok:
            passed = left == right
            detail = "JSON 结果一致" if passed else "JSON 结果不一致"
        else:
            passed = output.strip() == _text(value).strip()
            detail = "JSON 解析失败，按字符串比较，结果一致" if passed else "JSON 解析失败，按字符串比较，结果不一致"

    return {"score": 1.0 if passed else 0.0, "verdict": "passed" if passed else "failed", "detail": detail}


def _score_semantic(rules: dict[str, Any], output: str, expected: str,
                    trace: dict[str, Any] | None,
                    model_scorer: Callable[[dict[str, Any], str, str], Any] | None,
                    judge_resolver: Callable[[str], dict[str, Any] | None] | None) -> dict[str, Any]:
    """语义指标评分：指标模板渲染成 criteria，交给评委模型判定，产出维度明细。"""
    from .semantics import SEMANTIC_METRICS, render_criteria

    metric = str(rules.get("metric") or "").strip()
    template = SEMANTIC_METRICS.get(metric)
    if not template:
        return {"score": 0.0, "verdict": "invalid_rubric",
                "detail": f"未知语义指标：{metric or '（空）'}"}
    expect = rules.get("expect") if isinstance(rules.get("expect"), dict) else {}
    missing = [key for key in template.get("required", []) if not expect.get(key)]
    if missing:
        return {"score": 0.0, "verdict": "invalid_rubric",
                "detail": f"语义指标 {metric} 缺少参数：{'、'.join(missing)}"}
    if template.get("needs_trace") and not (isinstance(trace, dict) and trace):
        return {"score": 0.0, "verdict": "not_scored", "detail": "轨迹不可用，未评分"}

    judge_model_id = str(rules.get("judgeModelId") or "").strip()
    resolver = judge_resolver or _resolve_judge
    judge = resolver(judge_model_id)
    if not judge:
        return {"score": 0.0, "verdict": "invalid_rubric",
                "detail": f"找不到判分模型：{judge_model_id}"}

    judge_rubric = {
        "prompt": f"按语义指标 {metric} 判定这次回答的质量",
        "criteria": render_criteria(metric, expect, trace),
    }
    scorer = model_scorer or judge.get("scorer")
    result = score_with_model(judge_rubric, output, expected, scorer)
    if result["verdict"] in {"passed", "failed"}:
        result["metrics"] = {
            metric: {
                "score": result["score"],
                "detail": result["detail"],
                "judge": str(judge.get("name") or judge_model_id or "默认模型"),
                "label": str(template.get("label") or metric),
            }
        }
    return result


def _score_multi(rules: dict[str, Any], output: str, expected: str,
                  model_scorer: Callable[[dict[str, Any], str, str], Any] | None,
                  trace: dict[str, Any] | None,
                  judge_resolver: Callable[[str], dict[str, Any] | None] | None,
                  depth: int) -> dict[str, Any]:
    """复合规则：子规则全过才算过（all），或任一子规则过就算过（any）。"""
    children = rules.get("rules")
    mode = str(rules.get("mode") or "").strip()
    if not isinstance(children, list) or not children or mode not in {"all", "any"}:
        return {"score": 0.0, "verdict": "invalid_rubric", "detail": "multi 规则需要非空 rules 与合法 mode"}
    if depth >= MAX_RULE_DEPTH:
        return {"score": 0.0, "verdict": "invalid_rubric", "detail": "multi 规则嵌套过深"}
    results = [_score(output, expected, child if isinstance(child, dict) else {},
                      model_scorer, trace, judge_resolver, depth + 1) for child in children]
    passed_count = sum(1 for item in results if item["verdict"] == "passed")
    passed = passed_count == len(results) if mode == "all" else passed_count > 0
    score = sum(item["score"] for item in results) / len(results)
    detail = "；".join(f"{item['verdict']}：{item['detail']}" for item in results)
    merged: dict[str, Any] = {}
    for item in results:
        merged.update(item.get("metrics") or {})
    result = {"score": score, "verdict": "passed" if passed else "failed", "detail": detail}
    if merged:
        result["metrics"] = merged
    return result
