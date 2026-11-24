"""语义评分与参数级工具断言。

对应规格 S-005。先写期望，再改实现。
"""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from ...infrastructure.evaluation_store import EvaluationStore
from . import score_case
from .analysis import build_trace


def fake_reply(score: float = 0.8, verdict: str = "passed", reason: str = "判定理由") -> str:
    return json.dumps({"score": score, "verdict": verdict, "reason": reason}, ensure_ascii=False)


def capturing_scorer(store: dict):
    def scorer(rubric, actual_output, expected_output):
        store["rubric"] = rubric
        store["actual"] = actual_output
        store["expected"] = expected_output
        return fake_reply()
    return scorer


class SemanticRubricTests(unittest.TestCase):
    def test_semantic_metric_returns_score_and_dimension_detail(self):
        store: dict = {}
        result = score_case("这是关于客服系统的回答", "",
                            {"type": "semantic", "metric": "topic_adherence",
                             "expect": {"topics": ["客服系统"]}},
                            model_scorer=capturing_scorer(store))
        self.assertEqual(result["verdict"], "passed")
        self.assertEqual(result["score"], 0.8)
        metrics = result["metrics"]["topic_adherence"]
        self.assertEqual(metrics["score"], 0.8)
        self.assertEqual(metrics["detail"], "判定理由")
        self.assertEqual(metrics["label"], "话题贴合度")
        self.assertTrue(metrics["judge"])
        self.assertIn("客服系统", store["rubric"]["criteria"])

    def test_unknown_metric_is_invalid_rubric(self):
        result = score_case("回答", "", {"type": "semantic", "metric": "no_such_metric"})
        self.assertEqual(result["verdict"], "invalid_rubric")
        self.assertNotIn("metrics", result)

    def test_missing_expect_parameter_is_invalid_rubric(self):
        result = score_case("回答", "", {"type": "semantic", "metric": "topic_adherence"})
        self.assertEqual(result["verdict"], "invalid_rubric")
        self.assertIn("topics", result["detail"])

    def test_unknown_judge_model_is_invalid_rubric(self):
        result = score_case("回答", "",
                            {"type": "semantic", "metric": "answer_relevance",
                             "judgeModelId": "model-not-exist"},
                            judge_resolver=lambda model_id: None)
        self.assertEqual(result["verdict"], "invalid_rubric")
        self.assertIn("model-not-exist", result["detail"])

    def test_judge_model_is_recorded_in_metrics(self):
        result = score_case("回答", "",
                            {"type": "semantic", "metric": "answer_relevance",
                             "judgeModelId": "model-x"},
                            judge_resolver=lambda model_id: {
                                "name": "judge-x",
                                "scorer": lambda rubric, actual, expected: fake_reply(),
                            })
        self.assertEqual(result["verdict"], "passed")
        self.assertEqual(result["metrics"]["answer_relevance"]["judge"], "judge-x")

    def test_model_failure_is_scorer_unavailable(self):
        def broken(rubric, actual_output, expected_output):
            raise RuntimeError("模型炸了")
        result = score_case("回答", "", {"type": "semantic", "metric": "answer_relevance"},
                            model_scorer=broken)
        self.assertEqual(result["verdict"], "scorer_unavailable")
        self.assertEqual(result["score"], 0.0)
        self.assertNotIn("metrics", result)

    def test_trajectory_quality_receives_trace_summary(self):
        store: dict = {}
        trace = {"agent": "skills", "counts": {"step": 3, "clarify": 1},
                 "tools": ["retrieval"], "tokens": 10, "latencyMs": 20}
        result = score_case("回答", "",
                            {"type": "semantic", "metric": "trajectory_quality",
                             "expect": {"mustTools": ["retrieval"], "maxSteps": 5}},
                            model_scorer=capturing_scorer(store), trace=trace)
        self.assertEqual(result["verdict"], "passed")
        criteria = store["rubric"]["criteria"]
        self.assertIn("retrieval", criteria)
        self.assertIn("3", criteria)

    def test_trajectory_quality_without_trace_is_not_scored(self):
        result = score_case("回答", "", {"type": "semantic", "metric": "trajectory_quality"})
        self.assertEqual(result["verdict"], "not_scored")

    def test_multi_merges_metric_details(self):
        store: dict = {}
        trace = {"agent": "skills", "counts": {"step": 1}, "tools": ["retrieval"]}
        result = score_case("回答", "",
                            {"type": "multi", "mode": "all", "rules": [
                                {"type": "semantic", "metric": "answer_relevance"},
                                {"type": "trace", "expect": {"expectTools": ["retrieval"]}},
                            ]},
                            model_scorer=capturing_scorer(store), trace=trace)
        self.assertEqual(result["verdict"], "passed")
        self.assertIn("answer_relevance", result["metrics"])


class ToolCallAssertionTests(unittest.TestCase):
    def trace_with_calls(self):
        events = [
            {"event": {"type": "tool_start", "toolName": "检索",
                       "arguments": {"query": "退货政策", "limit": 5}}},
            {"event": {"type": "tool_start", "toolName": "写库",
                       "arguments": {"token": "secret-value", "note": "x" * 60}}},
        ]
        return build_trace(events, agent="skills")

    def test_build_trace_collects_tool_calls_with_sanitized_args(self):
        trace = self.trace_with_calls()
        calls = trace["toolCalls"]
        self.assertEqual([item["tool"] for item in calls], ["检索", "写库"])
        self.assertEqual(calls[0]["args"], {"query": "退货政策", "limit": 5})
        self.assertEqual(len(calls[1]["args"]["note"]), 40)
        self.assertNotIn("token", calls[1]["args"])

    def test_expect_tool_calls_matches_name_and_arguments(self):
        result = score_case("", "", {"type": "trace", "expect": {"expectToolCalls": [
            {"tool": "检索", "argsContain": ["退货"], "argsMatch": {"limit": 5}}]}},
            trace=self.trace_with_calls())
        self.assertEqual(result["verdict"], "passed")

    def test_expect_tool_calls_reports_missing_argument(self):
        result = score_case("", "", {"type": "trace", "expect": {"expectToolCalls": [
            {"tool": "检索", "argsContain": ["发票"]}]}},
            trace=self.trace_with_calls())
        self.assertEqual(result["verdict"], "failed")
        self.assertIn("发票", result["detail"])

    def test_expect_tool_calls_reports_missing_tool(self):
        result = score_case("", "", {"type": "trace", "expect": {"expectToolCalls": [
            {"tool": "退款"}]}},
            trace=self.trace_with_calls())
        self.assertEqual(result["verdict"], "failed")
        self.assertIn("退款", result["detail"])

    def test_min_tool_calls_is_enforced(self):
        passed = score_case("", "", {"type": "trace", "expect": {"minToolCalls": 2}},
                            trace=self.trace_with_calls())
        failed = score_case("", "", {"type": "trace", "expect": {"minToolCalls": 3}},
                            trace=self.trace_with_calls())
        self.assertEqual(passed["verdict"], "passed")
        self.assertEqual(failed["verdict"], "failed")
        self.assertIn("工具调用次数", failed["detail"])


class MetricStorageTests(unittest.TestCase):
    def test_metrics_round_trip_through_store(self):
        with tempfile.TemporaryDirectory() as root:
            store = EvaluationStore(Path(root) / "evaluation.db")
            dataset = store.create_dataset("集", "通用")
            case = store.add_case(dataset["dataset_id"], "输入")
            run = store.create_run(dataset["dataset_id"], "chat", "")
            store.save_result(run["eval_run_id"], case["case_id"], 0.8, "passed", "理由",
                              metrics={"topic_adherence": {"score": 0.8, "detail": "理由", "judge": "j"}})
            rows = store.list_results(run["eval_run_id"])
            self.assertEqual(rows[0]["metrics"]["topic_adherence"]["score"], 0.8)


if __name__ == "__main__":
    unittest.main()
