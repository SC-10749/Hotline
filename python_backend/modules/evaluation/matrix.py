"""评测矩阵：多 run × 样本的并排聚合。

对应规格 S-006。这里只放纯函数，不碰存储与路由。
"""
from __future__ import annotations

from typing import Any

# 只有真的判过分的样本才计入可评覆盖率。
GRADED_VERDICTS = {"passed", "failed", "flaky"}
# 多轮合并时无通过情况下取判定值的优先顺序。
_FALLBACK_ORDER = ["timeout", "invalid_rubric", "scorer_unavailable", "not_scored", "skipped"]


def _merge_cells(results: list[dict[str, Any]], run_id: str) -> dict[str, dict[str, Any]]:
    """把一次运行里同一样本的多轮结果合并成一格。"""
    grouped: dict[str, list[dict[str, Any]]] = {}
    for item in results or []:
        if not isinstance(item, dict):
            continue
        case_id = str(item.get("case_id") or "")
        if not case_id:
            continue
        grouped.setdefault(case_id, []).append(item)

    cells: dict[str, dict[str, Any]] = {}
    for case_id, rows in grouped.items():
        verdicts = [str(row.get("verdict") or "") for row in rows]
        passed_epochs = sum(1 for verdict in verdicts if verdict == "passed")
        if passed_epochs == len(verdicts):
            verdict = "passed"
        elif passed_epochs > 0:
            verdict = "flaky"
        else:
            verdict = ""
            for candidate in _FALLBACK_ORDER:
                if candidate in verdicts:
                    verdict = candidate
                    break
            if not verdict:
                verdict = verdicts[0] if verdicts else "not_scored"
        scores = [float(row.get("score") or 0.0) for row in rows]
        metrics: dict[str, Any] = {}
        for row in rows:
            for name, value in (row.get("metrics") or {}).items():
                metrics.setdefault(name, value)
        failure_kind = ""
        for row in rows:
            if row.get("failure_kind"):
                failure_kind = str(row["failure_kind"])
                break
        cells[case_id] = {
            "runId": run_id,
            "verdict": verdict,
            "score": round(sum(scores) / len(scores), 4) if scores else 0.0,
            "graded": verdict in GRADED_VERDICTS,
            "epochs": len(rows),
            "passedEpochs": passed_epochs,
            "failureKind": failure_kind,
            "metrics": metrics,
        }
    return cells


def _change(base: dict[str, Any] | None, cell: dict[str, Any] | None) -> str:
    """相对基线列的变化；只看是否通过。"""
    if base is None:
        return "added"
    if cell is None:
        return "removed"
    base_passed = base.get("verdict") == "passed"
    cell_passed = cell.get("verdict") == "passed"
    if base_passed == cell_passed:
        return "unchanged"
    return "improved" if cell_passed else "regressed"


def build_matrix(runs: list[dict[str, Any]] | None,
                 results_by_run: dict[str, list[dict[str, Any]]] | None) -> dict[str, Any]:
    """把多次运行 × 样本聚成一张矩阵。

    runs 的顺序即列顺序，第一个是基线。
    """
    run_list = [item for item in (runs or []) if isinstance(item, dict)]
    cells_by_run = {str(run.get("eval_run_id") or ""): _merge_cells(
        (results_by_run or {}).get(str(run.get("eval_run_id") or ""), []),
        str(run.get("eval_run_id") or "")) for run in run_list}

    case_ids = sorted({case_id for cells in cells_by_run.values() for case_id in cells})
    rows: list[dict[str, Any]] = []
    for case_id in case_ids:
        cells: list[dict[str, Any]] = []
        for index, run in enumerate(run_list):
            run_id = str(run.get("eval_run_id") or "")
            cell = cells_by_run.get(run_id, {}).get(case_id)
            base_cell = cells_by_run.get(str(run_list[0].get("eval_run_id") or ""), {}).get(case_id)
            entry = dict(cell) if cell else {"runId": run_id, "verdict": "", "score": 0.0,
                                             "graded": False, "epochs": 0, "passedEpochs": 0,
                                             "failureKind": "", "metrics": {}}
            entry["change"] = _change(base_cell, cell) if index > 0 else "unchanged"
            cells.append(entry)
        best = None
        for entry in cells:
            if not entry.get("verdict"):
                continue
            if best is None or entry["score"] > best["score"]:
                best = {"runId": entry["runId"], "score": entry["score"], "verdict": entry["verdict"]}
        rows.append({"caseId": case_id, "cells": cells, "best": best})

    run_summaries: dict[str, dict[str, Any]] = {}
    run_views: list[dict[str, Any]] = []
    for run in run_list:
        run_id = str(run.get("eval_run_id") or "")
        cells = cells_by_run.get(run_id, {})
        total = len(cells)
        graded = sum(1 for cell in cells.values() if cell.get("graded"))
        passed = sum(1 for cell in cells.values() if cell.get("verdict") == "passed")
        summary = {"graded": graded, "total": total,
                   "coverage": round(graded / total, 4) if total else 0.0,
                   "passed": passed, "failed": graded - passed}
        run_summaries[run_id] = summary
        run_views.append({
            "runId": run_id,
            "agent": str(run.get("agent") or ""),
            "status": str(run.get("status") or ""),
            "datasetId": str(run.get("dataset_id") or ""),
            "epochs": int(run.get("epochs") or 1),
            "createdAt": str(run.get("created_at") or ""),
            "passRate": round(passed / graded, 4) if graded else 0.0,
            **summary,
        })

    datasets = {view["datasetId"] for view in run_views}
    return {"sameDataset": len(datasets) <= 1, "runs": run_views, "rows": rows,
            "summary": run_summaries}
