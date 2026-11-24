"""评测可读性：失败分类派生与测评集最近运行摘要。

对应规格 S-007。这里只放纯函数，不碰存储与路由。
"""
from __future__ import annotations

from typing import Any

# rubric 类型 -> 失败分类：规则类型本身就是失败原因的证据。
RUBRIC_FAILURE_KINDS = {
    "contains": "missing_keyword",
    "equals": "output_mismatch",
    "json_equals": "json_mismatch",
    "model": "semantic_mismatch",
    "semantic": "semantic_mismatch",
    "trace": "trace_assertion_failed",
    "multi": "assertion_failed",
}


def classify_failure(verdict: str, rubric: dict[str, Any] | None = None,
                     trace: dict[str, Any] | None = None, output: str = "",
                     expected_output: str = "") -> str:
    """按证据派生失败分类；判通过的样本没有分类。

    顺序：超时 / 评委不可用 / rubric 显式声明 / 工具错误 / 空输出 / 规则类型 / 兜底。
    """
    if verdict == "passed":
        return ""
    if verdict == "timeout":
        return "timeout"
    if verdict == "scorer_unavailable":
        return "judge_unavailable"
    if verdict in {"invalid_rubric", "not_scored"}:
        return verdict
    rules = rubric if isinstance(rubric, dict) else {}
    explicit = str(rules.get("failureKind") or "").strip()
    if explicit:
        return explicit
    counts = (trace or {}).get("counts") or {}
    if int(counts.get("tool_error") or 0) > 0:
        return "tool_error"
    if not str(output or "").strip():
        # 助手没产出内容是根因，比「哪条规则没过」更值得先说。
        return "empty_output"
    kind = str(rules.get("type") or "").strip()
    derived = RUBRIC_FAILURE_KINDS.get(kind)
    if derived:
        return derived
    if not kind and str(expected_output or "").strip():
        # 没有规则类型时按「输出包含期望输出」判定。
        return "missing_keyword"
    return "assertion_failed"


def dataset_cards(datasets: list[dict[str, Any]] | None,
                  runs: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    """给每个测评集补上最近一次运行的摘要；没有运行过时 lastRun 为 None。"""
    latest: dict[str, dict[str, Any]] = {}
    for run in runs or []:
        if not isinstance(run, dict):
            continue
        dataset_id = str(run.get("dataset_id") or "")
        if not dataset_id:
            continue
        current = latest.get(dataset_id)
        if current is None or str(run.get("created_at") or "") > str(current.get("created_at") or ""):
            latest[dataset_id] = run
    cards: list[dict[str, Any]] = []
    for dataset in datasets or []:
        if not isinstance(dataset, dict):
            continue
        card = dict(dataset)
        run = latest.get(str(dataset.get("dataset_id") or ""))
        summary = (run or {}).get("summary") or {}
        card["lastRun"] = None if not run else {
            "runId": str(run.get("eval_run_id") or ""),
            "status": str(run.get("status") or ""),
            "agent": str(run.get("agent") or ""),
            "epochs": int(run.get("epochs") or 1),
            "createdAt": str(run.get("created_at") or ""),
            "passRate": summary.get("passRate") if isinstance(summary, dict) else None,
        }
        cards.append(card)
    return cards
