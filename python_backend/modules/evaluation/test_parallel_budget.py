"""并行跑批与预算护栏。

对应规格 S-004。先写期望，再改实现。
"""
from __future__ import annotations

import tempfile
import threading
import time
import unittest
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from ...api.routers.evaluation import create_evaluation_router
from ...infrastructure.evaluation_store import EvaluationStore


class SlowService:
    """每次执行固定耗时，并记录并发峰值。"""

    def __init__(self, delay: float = 0.3, tokens: int = 100, fail_on: str = ""):
        self.delay = delay
        self.tokens = tokens
        self.fail_on = fail_on
        self.lock = threading.Lock()
        self.active = 0
        self.peak = 0
        self.runs = 0

    def create(self, request):
        with self.lock:
            self.runs += 1
            index = self.runs
        return {"run_id": f"run-{index}", "status": "queued",
                "conversation_id": request.conversation_id}

    def get_run(self, run_id):
        with self.lock:
            self.active += 1
            self.peak = max(self.peak, self.active)
        try:
            time.sleep(self.delay)
            return {"run_id": run_id, "status": "completed", "error": None}
        finally:
            with self.lock:
                self.active -= 1

    def get_events(self, run_id, event_id=0):
        if self.fail_on and self.fail_on in run_id:
            raise RuntimeError("执行服务内部错误")
        return [{"event_id": 1, "event": {"type": "usage", "content": "模型用量",
                                          "usage": {"totalTokens": self.tokens}}}]


class FailingService(SlowService):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.failed_conversations = set()

    def create(self, request):
        result = super().create(request)
        self.failed_conversations.add(request.conversation_id)
        return result

    def get_events(self, run_id, event_id=0):
        if self.failed_conversations:
            # 只让第一个样本的事件读取失败，其它样本正常。
            if not getattr(self, "_blown", False):
                self._blown = True
                raise RuntimeError("执行服务内部错误")
        return super().get_events(run_id, event_id)


class ParallelBudgetTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = EvaluationStore(Path(self.temp.name) / "evaluation.db")
        self.service = SlowService()
        self.client = self.build_client()
        dataset = self.client.post("/evaluation/datasets", json={
            "name": "并发验收", "datasetType": "通用"}).json()["dataset"]
        self.dataset_id = dataset["dataset_id"]

    def build_client(self):
        app = FastAPI()
        app.include_router(create_evaluation_router(self.store, self.service))
        return TestClient(app)

    def add_cases(self, count: int):
        self.case_ids = []
        for index in range(count):
            response = self.client.post(f"/evaluation/datasets/{self.dataset_id}/cases", json={
                "input": f"问题{index}", "expectedOutput": "",
                "rubric": {"type": "always"}})
            self.case_ids.append(response.json()["case"]["case_id"])

    def run_evaluation(self, **extra):
        payload = {"datasetId": self.dataset_id, "agent": "chat", "epochs": 1}
        payload.update(extra)
        response = self.client.post("/evaluation/runs", json=payload)
        self.assertEqual(response.status_code, 200)
        run_id = response.json()["run"]["eval_run_id"]
        for _ in range(300):
            detail = self.client.get(f"/evaluation/runs/{run_id}").json()
            if detail["run"]["status"] in {"completed", "failed", "blocked", "cancelled"}:
                return detail
            time.sleep(0.05)
        self.fail("测评未在预期时间内结束")

    def test_default_concurrency_is_serial(self):
        self.add_cases(1)
        detail = self.run_evaluation()
        self.assertEqual(detail["run"]["summary"]["concurrency"], 1)
        self.assertEqual(detail["results"][0]["verdict"], "passed")

    def test_parallel_execution_is_faster_than_serial(self):
        self.add_cases(3)
        self.service.delay = 0.4
        started = time.monotonic()
        detail = self.run_evaluation(concurrency=3)
        elapsed = time.monotonic() - started
        self.assertEqual(len(detail["results"]), 3)
        self.assertGreaterEqual(self.service.peak, 2)
        self.assertLess(elapsed, 1.0)

    def test_results_keep_sample_order(self):
        self.add_cases(3)
        detail = self.run_evaluation(concurrency=3)
        case_ids = [item["case_id"] for item in detail["results"]]
        # 数据集样本顺序是 (created_at, case_id)，case_id 随机生成 → 按字典序。
        self.assertEqual(case_ids, sorted(self.case_ids))

    def test_broken_sample_does_not_stop_others(self):
        self.add_cases(3)
        self.service = FailingService(delay=0.05)
        self.client = self.build_client()
        detail = self.run_evaluation(concurrency=2)
        verdicts = [item["verdict"] for item in detail["results"]]
        self.assertEqual(len(verdicts), 3)
        self.assertEqual(verdicts.count("passed"), 2)

    def test_token_budget_skips_remaining_samples(self):
        self.add_cases(3)
        self.service.tokens = 100
        detail = self.run_evaluation(concurrency=1, budgetTokens=150)
        summary = detail["run"]["summary"]
        self.assertTrue(summary["budgetExhausted"])
        self.assertEqual(summary["skippedCount"], 1)
        self.assertEqual(summary["tokensUsed"], 200)
        verdicts = sorted(item["verdict"] for item in detail["results"])
        self.assertEqual(verdicts, ["passed", "passed", "skipped"])

    def test_pass_rate_ignores_skipped_samples(self):
        self.add_cases(3)
        self.service.tokens = 100
        detail = self.run_evaluation(concurrency=1, budgetTokens=150)
        summary = detail["run"]["summary"]
        self.assertEqual(summary["passRate"], 1.0)
        self.assertEqual(summary["resultCount"], 3)

    def test_time_budget_skips_remaining_samples(self):
        self.add_cases(3)
        self.service.delay = 0.6
        detail = self.run_evaluation(concurrency=1, budgetSeconds=1)
        summary = detail["run"]["summary"]
        self.assertTrue(summary["budgetExhausted"])
        self.assertEqual(summary["skippedCount"], 1)

    def test_sample_budget_skips_remaining_samples(self):
        self.add_cases(3)
        detail = self.run_evaluation(concurrency=1, budgetSamples=2)
        summary = detail["run"]["summary"]
        self.assertTrue(summary["budgetExhausted"])
        self.assertEqual(summary["skippedCount"], 1)
        self.assertEqual(summary["budgetSamples"], 2)
        verdicts = sorted(item["verdict"] for item in detail["results"])
        self.assertEqual(verdicts, ["passed", "passed", "skipped"])

    def test_skipped_samples_do_not_lower_pass_at_k(self):
        self.add_cases(3)
        detail = self.run_evaluation(concurrency=1, budgetSamples=1)
        summary = detail["run"]["summary"]
        self.assertEqual(summary["skippedCount"], 2)
        self.assertEqual(summary["passAtK"], 1.0)
        self.assertEqual(summary["flakyRate"], 0.0)

    def test_estimated_cost_uses_price(self):
        self.add_cases(1)
        self.service.tokens = 1000
        detail = self.run_evaluation(concurrency=1, pricePerMTok=2.0)
        summary = detail["run"]["summary"]
        self.assertAlmostEqual(summary["estimatedCostUsd"], 0.002, places=6)


if __name__ == "__main__":
    unittest.main()
