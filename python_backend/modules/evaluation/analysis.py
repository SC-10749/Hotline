"""测评分析能力：轨迹提取、轨迹断言、门禁判定、运行出处。

对应规格 S-002 / S-005。这里只放纯函数，不碰存储与路由。
"""
from __future__ import annotations

import hashlib
import operator
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

TRACE_EXPECT_KEYS = {"agent", "minClarify", "maxClarify", "expectTools", "forbidTools",
                     "maxToolErrors", "minSteps", "minTurns", "maxTurns",
                     "expectToolCalls", "minToolCalls"}
GATE_METRICS = {"passRate", "passAtK", "flakyRate", "avgLatencyMs", "avgTokens", "avgTurns",
                "failedCount", "caseCount", "passedCount", "resultCount",
                "tokensUsed", "skippedCount"}
GATE_OPS = {">=": operator.ge, "<=": operator.le, ">": operator.gt, "<": operator.lt,
            "==": operator.eq}
# 工具参数只留键名与前 40 个字符；凭据类参数整条丢掉。
ARG_VALUE_LIMIT = 40
_CREDENTIAL_KEY = re.compile(r"token|secret|password|passwd|credential|authorization|apikey|accesskey|privatekey")


def _is_credential_key(name: str) -> bool:
    """凭据类参数名：去掉分隔符后仍命中关键词，或就叫 key。"""
    normalized = re.sub(r"[^a-z0-9]", "", str(name).lower())
    return normalized == "key" or bool(_CREDENTIAL_KEY.search(normalized))


def _safe_args(arguments: Any) -> dict[str, Any]:
    """工具参数摘要：值只留前 40 字符，凭据类参数整条丢弃。"""
    if not isinstance(arguments, dict):
        return {}
    safe: dict[str, Any] = {}
    for key, value in arguments.items():
        name = str(key)
        if _is_credential_key(name):
            continue
        if isinstance(value, str):
            safe[name] = value[:ARG_VALUE_LIMIT]
        elif isinstance(value, (int, float, bool)) or value is None:
            safe[name] = value
        else:
            safe[name] = str(value)[:ARG_VALUE_LIMIT]
    return safe


def build_trace(events: list[dict[str, Any]] | None, agent: str = "", latency_ms: int = 0) -> dict[str, Any]:
    """把一次执行的事件流压成可断言的轨迹摘要。"""
    counts: dict[str, int] = {}
    tools: list[str] = []
    tool_calls: list[dict[str, Any]] = []
    tokens = 0
    run_total = 0
    for item in events or []:
        event = item.get("event") if isinstance(item, dict) and "event" in item else item
        if not isinstance(event, dict):
            continue
        event_type = str(event.get("type") or "")
        if not event_type:
            continue
        counts[event_type] = counts.get(event_type, 0) + 1
        if event_type == "tool_start":
            name = str(event.get("tool") or event.get("toolName") or "")
            if name and name not in tools:
                tools.append(name)
            arguments = event.get("arguments")
            if not isinstance(arguments, dict):
                arguments = event.get("args") if isinstance(event.get("args"), dict) else {}
            tool_calls.append({"tool": name, "args": _safe_args(arguments)})
        if event_type == "tool_end" and event.get("status") == "error":
            counts["tool_error"] = counts.get("tool_error", 0) + 1
        if event_type == "usage":
            usage = event.get("usage") or {}
            tokens += int(usage.get("totalTokens") or 0)
            run_total = max(run_total, int(usage.get("runTotal") or 0))
    return {"agent": agent or "", "counts": counts, "tools": tools, "toolCalls": tool_calls,
            "tokens": run_total or tokens, "latencyMs": int(latency_ms or 0)}


def merge_traces(traces: list[dict[str, Any]] | None) -> dict[str, Any]:
    """把多轮的轨迹摘要合成一份：计数相加、工具取并集、耗时与 token 累加。"""
    merged: dict[str, Any] = {"agent": "", "counts": {}, "tools": [], "toolCalls": [],
                              "tokens": 0, "latencyMs": 0}
    for trace in traces or []:
        if not isinstance(trace, dict):
            continue
        merged["agent"] = merged["agent"] or str(trace.get("agent") or "")
        for key, value in (trace.get("counts") or {}).items():
            merged["counts"][key] = merged["counts"].get(key, 0) + int(value or 0)
        for tool in trace.get("tools") or []:
            if tool not in merged["tools"]:
                merged["tools"].append(tool)
        merged["toolCalls"].extend(trace.get("toolCalls") or [])
        merged["tokens"] += int(trace.get("tokens") or 0)
        merged["latencyMs"] += int(trace.get("latencyMs") or 0)
    merged["counts"]["turns"] = len(traces or [])
    return merged


def _arg_text(args: dict[str, Any]) -> str:
    return " ".join(f"{key}={value}" for key, value in (args or {}).items())


def _match_tool_call(expectation: dict[str, Any], calls: list[dict[str, Any]]) -> str:
    """检查一条工具调用期望；满足返回空串，不满足返回差在哪一项。"""
    tool = str(expectation.get("tool") or "")
    candidates = [item for item in calls if str(item.get("tool") or "") == tool]
    if not candidates:
        return f"未调用工具 {tool}"
    for need in expectation.get("argsContain") or []:
        needle = str(need)
        if not any(needle in _arg_text(item.get("args") or {}) for item in candidates):
            return f"工具 {tool} 的参数未包含 {needle}"
    for key, value in (expectation.get("argsMatch") or {}).items():
        ok = any(str((item.get("args") or {}).get(key)) == str(value) for item in candidates)
        if not ok:
            return f"工具 {tool} 的参数 {key} 不是 {value}"
    return ""


def score_trace(expect: Any, trace: Any) -> dict[str, Any]:
    """按 expect 里的条件检查轨迹；全部满足才通过，不满足时列出所有问题。"""
    if not isinstance(expect, dict) or not expect:
        return {"score": 0.0, "verdict": "invalid_rubric", "detail": "trace 规则缺少 expect 条件"}
    unknown = sorted(set(expect) - TRACE_EXPECT_KEYS)
    if unknown:
        return {"score": 0.0, "verdict": "invalid_rubric",
                "detail": f"trace 规则含未知键：{'、'.join(unknown)}"}
    if not isinstance(trace, dict) or not trace:
        return {"score": 0.0, "verdict": "not_scored", "detail": "轨迹不可用，未评分"}
    counts = trace.get("counts") or {}
    tools = list(trace.get("tools") or [])
    calls = list(trace.get("toolCalls") or [])
    problems: list[str] = []

    agent = expect.get("agent")
    if agent and trace.get("agent") != agent:
        problems.append(f"助手类型 {trace.get('agent') or '—'} 与期望 {agent} 不一致")

    clarify = int(counts.get("clarify") or 0)
    if expect.get("minClarify") is not None and clarify < int(expect["minClarify"]):
        problems.append(f"澄清次数 {clarify} 少于下限 {expect['minClarify']}")
    if expect.get("maxClarify") is not None and clarify > int(expect["maxClarify"]):
        problems.append(f"澄清次数 {clarify} 超过上限 {expect['maxClarify']}")

    for tool in expect.get("expectTools") or []:
        if tool not in tools:
            problems.append(f"未调用工具 {tool}")
    for tool in expect.get("forbidTools") or []:
        if tool in tools:
            problems.append(f"调用了禁止的工具 {tool}")

    for expectation in expect.get("expectToolCalls") or []:
        if not isinstance(expectation, dict) or not expectation.get("tool"):
            problems.append("expectToolCalls 里每项都要有 tool")
            continue
        problem = _match_tool_call(expectation, calls)
        if problem:
            problems.append(problem)

    if expect.get("minToolCalls") is not None:
        actual = len(calls) or int(counts.get("tool_start") or 0)
        if actual < int(expect["minToolCalls"]):
            problems.append(f"工具调用次数 {actual} 少于下限 {expect['minToolCalls']}")

    errors = int(counts.get("tool_error") or 0)
    if expect.get("maxToolErrors") is not None and errors > int(expect["maxToolErrors"]):
        problems.append(f"工具错误 {errors} 超过上限 {expect['maxToolErrors']}")

    steps = int(counts.get("step") or 0)
    if expect.get("minSteps") is not None and steps < int(expect["minSteps"]):
        problems.append(f"步骤数 {steps} 少于下限 {expect['minSteps']}")

    turns = int(counts.get("turns") or 0)
    if expect.get("minTurns") is not None and turns < int(expect["minTurns"]):
        problems.append(f"对话轮数 {turns} 少于下限 {expect['minTurns']}")
    if expect.get("maxTurns") is not None and turns > int(expect["maxTurns"]):
        problems.append(f"对话轮数 {turns} 超过上限 {expect['maxTurns']}")

    if problems:
        return {"score": 0.0, "verdict": "failed", "detail": "；".join(problems)}
    return {"score": 1.0, "verdict": "passed", "detail": "轨迹断言全部满足"}


def check_gates(gates: list[dict[str, Any]] | None, summary: dict[str, Any] | None,
                base_summary: dict[str, Any] | None = None) -> dict[str, Any]:
    """按配置的阈值检查一轮测评的汇总指标；指标缺失算未通过，不当作 0。"""
    checks: list[dict[str, Any]] = []
    for gate in gates or []:
        if not isinstance(gate, dict):
            continue
        label = str(gate.get("label") or gate.get("metric") or "未命名门禁")
        metric = str(gate.get("metric") or "")
        op = str(gate.get("op") or "")
        value = gate.get("value")
        actual = summary.get(metric) if isinstance(summary, dict) else None
        passed = False
        if metric not in GATE_METRICS or op not in GATE_OPS:
            detail = "门禁配置无效：指标或比较算子不支持"
        elif actual is None:
            detail = f"指标 {metric} 在本轮汇总里缺失"
        else:
            try:
                passed = bool(GATE_OPS[op](float(actual), float(value)))
            except (TypeError, ValueError):
                passed = False
                detail = "门禁取值无法比较"
            else:
                detail = ""
        check = {"label": label, "metric": metric, "op": op, "value": value,
                 "actual": actual, "passed": passed, "detail": detail}
        if base_summary is not None:
            check["actualBase"] = base_summary.get(metric) if isinstance(base_summary, dict) else None
        checks.append(check)
    return {"passed": all(check["passed"] for check in checks) if checks else True, "checks": checks}


def build_provenance(dataset: dict[str, Any] | None, agent: str, epochs: int,
                     model_name: str = "", commit: str = "",
                     skills: dict[str, str] | None = None) -> dict[str, Any]:
    """记录这一轮是在什么配置下跑出来的。"""
    dataset = dataset or {}
    return {
        "datasetId": dataset.get("dataset_id") or "",
        "datasetVersion": int(dataset.get("version") or 1),
        "caseCount": int(dataset.get("case_count") or 0),
        "agent": agent or "",
        "epochs": int(epochs or 1),
        "model": model_name or "",
        "commit": commit or "",
        "skills": dict(skills or {}),
        "createdAt": datetime.now(timezone.utc).isoformat(),
    }


def repo_commit(root: Path) -> str:
    """当前代码提交号；仓库不可用时返回空串，不让出处在测评时失败。"""
    try:
        result = subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(root),
                                capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.SubprocessError):
        return ""
    return result.stdout.strip() if result.returncode == 0 else ""


def skills_digest(root: Path) -> dict[str, str]:
    """仓库里各技能包正文的 sha256 前 12 位；出处随代码走，不取安装副本。"""
    skills_dir = Path(root) / "skills"
    if not skills_dir.is_dir():
        return {}
    digest: dict[str, str] = {}
    for path in sorted(skills_dir.glob("*/SKILL.md")):
        try:
            digest[path.parent.name] = hashlib.sha256(path.read_bytes()).hexdigest()[:12]
        except OSError:
            continue
    return digest
