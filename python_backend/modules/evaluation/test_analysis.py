"""Agent 测评增强：轨迹断言、复合规则、重复稳定性、运行出处、失败分类。

这些是规格 S-002 的可执行契约：先写期望，再改实现。
"""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from ...api.routers.evaluation import create_evaluation_router
from ...infrastructure.evaluation_store import EvaluationStore
from . import score_case
from .analysis import build_provenance, build_trace, check_gates


def trace_fixture(**overrides):
    trace = {"agent": "skills", "counts": {"clarify": 2, "tool_start": 1, "tool_error": 0, "step": 3},
             "tools": ["retrieval"], "tokens": 120, "latencyMs": 1500}
    trace.update(overrides)
    return trace


class TraceBuildingTests(unittest.TestCase):
    def test_counts_tools_tokens_and_latency(self):
        events = [
            {"event_id": 1, "event": {"type": "text", "content": "你好"}},
            {"event_id": 2, "event": {"type": "tool_start", "tool": "retrieval"}},
            {"event_id": 3, "event": {"type": "tool_end", "tool": "retrieval", "status": "error"}},
            {"event_id": 4, "event": {"type": "clarify", "content": "三个理解方向"}},
            {"event_id": 5, "event": {"type": "usage", "usage": {"totalTokens": 120}}},
        ]
        trace = build_trace(events, agent="skills", latency_ms=1500)
        self.assertEqual(trace["agent"], "skills")
        self.assertEqual(trace["counts"]["text"], 1)
        self.assertEqual(trace["counts"]["tool_start"], 1)
        self.assertEqual(trace["counts"]["tool_error"], 1)
        self.assertEqual(trace["counts"]["clarify"], 1)
        self.assertEqual(trace["tools"], ["retrieval"])
        self.assertEqual(trace["tokens"], 120)
        self.assertEqual(trace["latencyMs"], 1500)

    def test_run_total_usage_wins_over_sum(self):
        events = [
            {"event_id": 1, "event": {"type": "usage", "usage": {"totalTokens": 30}}},
            {"event_id": 2, "event": {"type": "usage", "usage": {"totalTokens": 30, "runTotal": 55}}},
        ]
        self.assertEqual(build_trace(events)["tokens"], 55)

    def test_accepts_raw_event_dicts(self):
        trace = build_trace([{"type": "clarify", "content": "x"}])
        self.assertEqual(trace["counts"]["clarify"], 1)


class TraceRuleTests(unittest.TestCase):
    def test_passes_when_every_expectation_is_met(self):
        result = score_case("", "", {"type": "trace", "expect": {
            "agent": "skills", "minClarify": 1, "maxClarify": 3,
            "expectTools": ["retrieval"], "forbidTools": ["shell"],
            "maxToolErrors": 0, "minSteps": 2}}, trace=trace_fixture())
        self.assertEqual(result["verdict"], "passed")
        self.assertEqual(result["score"], 1.0)

    def test_reports_every_missed_expectation(self):
        result = score_case("", "", {"type": "trace", "expect": {
            "minClarify": 1, "expectTools": ["retrieval"], "maxToolErrors": 0}},
            trace=trace_fixture(counts={"clarify": 0, "tool_error": 2, "step": 1}, tools=[]))
        self.assertEqual(result["verdict"], "failed")
        self.assertEqual(result["score"], 0.0)
        for fragment in ("澄清", "retrieval", "工具错误"):
            self.assertIn(fragment, result["detail"])

    def test_missing_expect_is_invalid_rubric(self):
        result = score_case("", "", {"type": "trace"}, trace=trace_fixture())
        self.assertEqual(result["verdict"], "invalid_rubric")

    def test_unknown_expect_key_is_invalid_rubric(self):
        result = score_case("", "", {"type": "trace", "expect": {"minTools": 2}}, trace=trace_fixture())
        self.assertEqual(result["verdict"], "invalid_rubric")
        self.assertIn("minTools", result["detail"])

    def test_missing_trace_is_not_scored(self):
        result = score_case("", "", {"type": "trace", "expect": {"minClarify": 1}}, trace=None)
        self.assertEqual(result["verdict"], "not_scored")
        self.assertEqual(result["score"], 0.0)

    def test_forbidden_tool_fails(self):
        result = score_case("", "", {"type": "trace", "expect": {"forbidTools": ["shell"]}},
                            trace=trace_fixture(tools=["retrieval", "shell"]))
        self.assertEqual(result["verdict"], "failed")


class MultiRuleTests(unittest.TestCase):
    def test_all_mode_fails_when_one_child_fails(self):
        rubric = {"type": "multi", "mode": "all", "rules": [
            {"type": "contains", "value": "A"}, {"type": "contains", "value": "B"}]}
        result = score_case("只有 A", "", rubric)
        self.assertEqual(result["verdict"], "failed")
        self.assertAlmostEqual(result["score"], 0.5)

    def test_any_mode_passes_when_one_child_passes(self):
        rubric = {"type": "multi", "mode": "any", "rules": [
            {"type": "contains", "value": "A"}, {"type": "contains", "value": "B"}]}
        result = score_case("只有 A", "", rubric)
        self.assertEqual(result["verdict"], "passed")
        self.assertAlmostEqual(result["score"], 0.5)

    def test_without_rules_is_invalid(self):
        result = score_case("x", "", {"type": "multi", "mode": "all"})
        self.assertEqual(result["verdict"], "invalid_rubric")

    def test_with_invalid_mode_is_invalid(self):
        result = score_case("x", "", {"type": "multi", "mode": "sometimes",
                                      "rules": [{"type": "always"}]})
        self.assertEqual(result["verdict"], "invalid_rubric")


class GateCheckTests(unittest.TestCase):
    def test_threshold_above_actual_fails(self):
        report = check_gates([{"label": "通过率", "metric": "passRate", "op": ">=", "value": 0.95}],
                             {"passRate": 0.9})
        self.assertFalse(report["passed"])
        self.assertEqual(report["checks"][0]["actual"], 0.9)

    def test_turn_count_metric_is_supported(self):
        report = check_gates([{"label": "轮数下限", "metric": "avgTurns", "op": ">=", "value": 1}],
                             {"avgTurns": 3.0})
        self.assertTrue(report["passed"])
        self.assertEqual(report["checks"][0]["actual"], 3.0)

    def test_missing_metric_fails_instead_of_counting_as_zero(self):
        report = check_gates([{"label": "不稳定率", "metric": "flakyRate", "op": "<=", "value": 0.2}],
                             {"passRate": 0.9})
        self.assertFalse(report["passed"])
        self.assertIsNone(report["checks"][0]["actual"])

    def test_unknown_operator_is_reported_as_failed_check(self):
        report = check_gates([{"label": "x", "metric": "passRate", "op": "~", "value": 1}],
                             {"passRate": 0.9})
        self.assertFalse(report["passed"])
        self.assertFalse(report["checks"][0]["passed"])

    def test_base_actual_is_reported_when_given(self):
        report = check_gates([{"label": "通过率", "metric": "passRate", "op": ">=", "value": 0.5}],
                             {"passRate": 0.9}, base_summary={"passRate": 0.7})
        self.assertTrue(report["passed"])
        self.assertEqual(report["checks"][0]["actualBase"], 0.7)


class ProvenanceTests(unittest.TestCase):
    def test_records_dataset_version_model_commit_and_skills(self):
        provenance = build_provenance(
            dataset={"dataset_id": "dataset-1", "version": 3, "case_count": 2},
            agent="chat", epochs=2, model_name="qwen-plus", commit="abc123",
            skills={"requirement-analysis": "deadbeef1234"})
        self.assertEqual(provenance["datasetId"], "dataset-1")
        self.assertEqual(provenance["datasetVersion"], 3)
        self.assertEqual(provenance["caseCount"], 2)
        self.assertEqual(provenance["epochs"], 2)
        self.assertEqual(provenance["model"], "qwen-plus")
        self.assertEqual(provenance["commit"], "abc123")
        self.assertEqual(provenance["skills"]["requirement-analysis"], "deadbeef1234")


class FakeService:
    """按 conversation_id 返回不同事件的假执行服务。"""

    def __init__(self, events_for):
        self.events_for = events_for
        self.by_run = {}
        self.counter = 0

    def create(self, request):
        self.counter += 1
        run_id = f"run-{self.counter}"
        self.by_run[run_id] = request.conversation_id
        return {"run_id": run_id, "status": "queued", "conversation_id": request.conversation_id}

    def get_run(self, run_id):
        if run_id not in self.by_run:
            return None
        return {"run_id": run_id, "status": "completed", "error": None}

    def get_events(self, run_id, event_id=0):
        conversation_id = self.by_run.get(run_id)
        if conversation_id is None:
            return []
        return [{"event_id": index + 1, "event": event}
                for index, event in enumerate(self.events_for(conversation_id))]


class AgentEvaluationRunTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = EvaluationStore(Path(self.temp.name) / "evaluation.db")
        self.service = FakeService(self.events_for)
        app = FastAPI()
        app.include_router(create_evaluation_router(self.store, self.service))
        self.client = TestClient(app)
        dataset = self.client.post("/evaluation/datasets", json={
            "name": "需求助手", "datasetType": "需求"}).json()["dataset"]
        self.dataset_id = dataset["dataset_id"]
        self.case_id = self.client.post(f"/evaluation/datasets/{self.dataset_id}/cases", json={
            "input": "我要一个客服系统", "expectedOutput": "",
            "rubric": {"type": "contains", "value": "OK"}}).json()["case"]["case_id"]

    def events_for(self, conversation_id):
        # 第 0 轮答对，第 1 轮答错，用来验证不稳定率
        if conversation_id.endswith(":0"):
            return [{"type": "text", "content": "OK"},
                    {"type": "tool_start", "tool": "retrieval"},
                    {"type": "clarify", "content": "三个方向"}]
        return [{"type": "text", "content": "不通过"},
                {"type": "tool_end", "tool": "retrieval", "status": "error"}]

    def run_evaluation(self, epochs=1):
        response = self.client.post("/evaluation/runs", json={
            "datasetId": self.dataset_id, "agent": "chat", "epochs": epochs})
        self.assertEqual(response.status_code, 200)
        run_id = response.json()["run"]["eval_run_id"]
        import time
        for _ in range(100):
            detail = self.client.get(f"/evaluation/runs/{run_id}").json()
            if detail["run"]["status"] in {"completed", "failed", "blocked", "cancelled"}:
                return detail
            time.sleep(0.05)
        self.fail("测评未在预期时间内结束")

    def test_single_epoch_keeps_existing_summary_semantics(self):
        detail = self.run_evaluation(epochs=1)
        summary = detail["run"]["summary"]
        self.assertEqual(summary["caseCount"], 1)
        self.assertEqual(summary["passedCount"], 1)
        self.assertEqual(summary["failedCount"], 0)
        self.assertEqual(summary["passRate"], 1.0)
        self.assertEqual(summary["epochs"], 1)
        self.assertEqual(summary["flakyRate"], 0.0)
        self.assertEqual(summary["passAtK"], 1.0)

    def test_repeated_epochs_produce_repeated_results_and_stability_metrics(self):
        detail = self.run_evaluation(epochs=2)
        summary = detail["run"]["summary"]
        self.assertEqual(summary["caseCount"], 1)
        self.assertEqual(summary["resultCount"], 2)
        self.assertEqual(summary["epochs"], 2)
        self.assertEqual(summary["passedCount"], 1)
        self.assertEqual(summary["flakyRate"], 1.0)
        self.assertEqual(summary["passAtK"], 0.0)
        self.assertEqual(sorted(item["epoch"] for item in detail["results"]), [0, 1])

    def test_failed_sample_carries_failure_kind(self):
        detail = self.run_evaluation(epochs=2)
        kinds = {item["epoch"]: item["failure_kind"] for item in detail["results"]}
        self.assertEqual(kinds[0], "")
        self.assertEqual(kinds[1], "tool_error")

    def test_run_records_provenance(self):
        detail = self.run_evaluation(epochs=1)
        provenance = detail["run"]["provenance"]
        self.assertEqual(provenance["datasetId"], self.dataset_id)
        self.assertEqual(provenance["epochs"], 1)
        self.assertIn("model", provenance)
        self.assertIn("skills", provenance)

    def test_trace_endpoint_returns_event_timeline(self):
        detail = self.run_evaluation(epochs=1)
        response = self.client.get(
            f"/evaluation/runs/{detail['run']['eval_run_id']}/trace",
            params={"caseId": self.case_id, "epoch": 0})
        self.assertEqual(response.status_code, 200)
        trace = response.json()["trace"]
        self.assertEqual(trace["counts"]["clarify"], 1)
        self.assertEqual(trace["tools"], ["retrieval"])
        self.assertTrue(trace["events"])
        self.assertEqual(trace["events"][0]["type"], "text")

    def test_trace_endpoint_404_for_unknown_case(self):
        detail = self.run_evaluation(epochs=1)
        response = self.client.get(
            f"/evaluation/runs/{detail['run']['eval_run_id']}/trace",
            params={"caseId": "case-none", "epoch": 0})
        self.assertEqual(response.status_code, 404)

    def test_gate_check_uses_configured_thresholds(self):
        self.client.put("/evaluation/config", json={
            "dimensions": [], "gates": [{"label": "通过率", "metric": "passRate", "op": ">=", "value": 0.9}]})
        detail = self.run_evaluation(epochs=1)
        response = self.client.post("/evaluation/gates/check", json={
            "target": detail["run"]["eval_run_id"]})
        self.assertEqual(response.status_code, 200)
        report = response.json()
        self.assertTrue(report["passed"])
        self.assertEqual(report["checks"][0]["actual"], 1.0)

    def test_snapshot_keeps_case_bodies(self):
        self.client.post(f"/evaluation/datasets/{self.dataset_id}/snapshots")
        snapshots = self.client.get(f"/evaluation/datasets/{self.dataset_id}/snapshots").json()["items"]
        payload = snapshots[0]["payload"]
        self.assertEqual(payload["cases"][0]["case_id"], self.case_id)
        self.assertEqual(payload["cases"][0]["input_text"], "我要一个客服系统")
        self.assertTrue(payload["sha256"])


if __name__ == "__main__":
    unittest.main()
