"""评测矩阵视图：多 run × 样本并排、相对判定、同题择优、可评覆盖率。

对应规格 S-006。先写期望，再改实现。
"""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from ...api.routers.evaluation import create_evaluation_router
from ...infrastructure.evaluation_store import EvaluationStore
from .matrix import build_matrix


def run_fixture(run_id: str, dataset_id: str = "dataset-a", agent: str = "chat") -> dict:
    return {"eval_run_id": run_id, "dataset_id": dataset_id, "agent": agent,
            "status": "completed", "epochs": 1, "created_at": "2026-11-23T00:00:00Z"}


def cell_fixture(case_id: str, verdict: str, score: float = 1.0, **extra) -> dict:
    return {"case_id": case_id, "verdict": verdict, "score": score,
            "failure_kind": "", "metrics": {}, "epoch": 0, **extra}


class MatrixBuildingTests(unittest.TestCase):
    def test_rows_are_case_union_and_columns_are_runs(self):
        matrix = build_matrix(
            [run_fixture("eval-a"), run_fixture("eval-b")],
            {"eval-a": [cell_fixture("case-1", "passed"), cell_fixture("case-2", "failed", 0.0)],
             "eval-b": [cell_fixture("case-1", "passed"), cell_fixture("case-3", "passed")]},
        )
        self.assertEqual([row["caseId"] for row in matrix["rows"]], ["case-1", "case-2", "case-3"])
        # case-2 只在基线里有 -> 该列标 removed；case-3 只在目标列有 -> 标 added。
        self.assertEqual(matrix["rows"][1]["cells"][1]["change"], "removed")
        self.assertEqual(matrix["rows"][2]["cells"][1]["change"], "added")
        self.assertEqual(matrix["rows"][0]["cells"][0]["change"], "unchanged")

    def test_change_is_relative_to_first_run(self):
        matrix = build_matrix(
            [run_fixture("eval-a"), run_fixture("eval-b")],
            {"eval-a": [cell_fixture("case-1", "failed", 0.0)],
             "eval-b": [cell_fixture("case-1", "passed")]},
        )
        self.assertEqual(matrix["rows"][0]["cells"][1]["change"], "improved")

    def test_regression_is_reported(self):
        matrix = build_matrix(
            [run_fixture("eval-a"), run_fixture("eval-b")],
            {"eval-a": [cell_fixture("case-1", "passed")],
             "eval-b": [cell_fixture("case-1", "failed", 0.0)]},
        )
        self.assertEqual(matrix["rows"][0]["cells"][1]["change"], "regressed")

    def test_best_picks_highest_score(self):
        matrix = build_matrix(
            [run_fixture("eval-a"), run_fixture("eval-b"), run_fixture("eval-c")],
            {"eval-a": [cell_fixture("case-1", "passed", 0.6)],
             "eval-b": [cell_fixture("case-1", "passed", 0.9)],
             "eval-c": [cell_fixture("case-1", "failed", 0.0)]},
        )
        self.assertEqual(matrix["rows"][0]["best"]["runId"], "eval-b")
        self.assertEqual(matrix["rows"][0]["best"]["score"], 0.9)

    def test_coverage_counts_only_graded_cells(self):
        matrix = build_matrix(
            [run_fixture("eval-a")],
            {"eval-a": [cell_fixture("case-1", "passed"),
                        cell_fixture("case-2", "skipped"),
                        cell_fixture("case-3", "not_scored")]},
        )
        run = matrix["runs"][0]
        self.assertEqual(run["total"], 3)
        self.assertEqual(run["graded"], 1)
        self.assertEqual(run["coverage"], 0.3333)
        self.assertEqual(matrix["summary"]["eval-a"]["coverage"], 0.3333)

    def test_multi_epoch_cells_merge_to_flaky(self):
        matrix = build_matrix(
            [run_fixture("eval-a")],
            {"eval-a": [cell_fixture("case-1", "passed"), cell_fixture("case-1", "failed", 0.0)]},
        )
        cell = matrix["rows"][0]["cells"][0]
        self.assertEqual(cell["verdict"], "flaky")
        self.assertEqual(cell["epochs"], 2)
        self.assertEqual(cell["passedEpochs"], 1)
        self.assertEqual(cell["score"], 0.5)

    def test_different_datasets_are_flagged(self):
        matrix = build_matrix(
            [run_fixture("eval-a", "dataset-a"), run_fixture("eval-b", "dataset-b")],
            {"eval-a": [], "eval-b": []},
        )
        self.assertFalse(matrix["sameDataset"])


class MatrixRouterTests(unittest.TestCase):
    def build_client(self, root: Path) -> TestClient:
        store = EvaluationStore(root / "evaluation.db")
        app = FastAPI()
        app.include_router(create_evaluation_router(store))
        return TestClient(app), store

    def test_matrix_endpoint_returns_matrix(self):
        with tempfile.TemporaryDirectory() as root:
            client, store = self.build_client(Path(root))
            dataset = store.create_dataset("集", "通用")
            case = store.add_case(dataset["dataset_id"], "输入")
            first = store.create_run(dataset["dataset_id"], "chat", "")
            second = store.create_run(dataset["dataset_id"], "chat", "")
            store.save_result(first["eval_run_id"], case["case_id"], 1.0, "passed", "好")
            store.save_result(second["eval_run_id"], case["case_id"], 0.0, "failed", "差")
            response = client.get(f"/evaluation/runs/matrix?runs={first['eval_run_id']},{second['eval_run_id']}")
            self.assertEqual(response.status_code, 200)
            payload = response.json()
            self.assertEqual(payload["rows"][0]["cells"][1]["change"], "regressed")
            self.assertEqual(payload["runs"][0]["coverage"], 1.0)

    def test_matrix_requires_two_runs(self):
        with tempfile.TemporaryDirectory() as root:
            client, _ = self.build_client(Path(root))
            response = client.get("/evaluation/runs/matrix?runs=eval-a")
            self.assertEqual(response.status_code, 400)

    def test_matrix_rejects_unknown_run(self):
        with tempfile.TemporaryDirectory() as root:
            client, _ = self.build_client(Path(root))
            response = client.get("/evaluation/runs/matrix?runs=eval-a,eval-missing")
            self.assertEqual(response.status_code, 404)


if __name__ == "__main__":
    unittest.main()
