"""评测可读性：失败分类派生与测评集最近运行摘要。

对应规格 S-007。先写期望，再改实现。
"""
from __future__ import annotations

import unittest

from .readability import classify_failure, dataset_cards


class FailureClassificationTests(unittest.TestCase):
    def test_passed_has_no_failure_kind(self):
        self.assertEqual(classify_failure("passed", {"type": "contains", "value": "x"}), "")

    def test_timeout_and_scorer_unavailable_are_kept(self):
        self.assertEqual(classify_failure("timeout"), "timeout")
        self.assertEqual(classify_failure("scorer_unavailable"), "judge_unavailable")

    def test_explicit_failure_kind_wins(self):
        kind = classify_failure("failed", {"failureKind": "policy_violation"},
                                {"counts": {"tool_error": 2}})
        self.assertEqual(kind, "policy_violation")

    def test_tool_error_is_evidence(self):
        kind = classify_failure("failed", {"type": "contains"}, {"counts": {"tool_error": 1}})
        self.assertEqual(kind, "tool_error")

    def test_rubric_type_derives_the_kind(self):
        expected = {
            "contains": "missing_keyword",
            "equals": "output_mismatch",
            "json_equals": "json_mismatch",
            "model": "semantic_mismatch",
            "semantic": "semantic_mismatch",
            "trace": "trace_assertion_failed",
            "multi": "assertion_failed",
        }
        for rubric_type, kind in expected.items():
            self.assertEqual(classify_failure("failed", {"type": rubric_type}, None, "实际输出"),
                             kind, rubric_type)

    def test_rule_without_type_is_treated_as_contains(self):
        self.assertEqual(classify_failure("failed", {}, None, "别的内容", "答案"), "missing_keyword")

    def test_empty_output_is_reported(self):
        self.assertEqual(classify_failure("failed", {"type": "multi"}, None, "  "), "empty_output")

    def test_empty_output_wins_over_the_rule_type(self):
        self.assertEqual(classify_failure("failed", {}, None, "", "答案"), "empty_output")

    def test_unknown_rule_falls_back_to_assertion_failed(self):
        kind = classify_failure("failed", {"type": "unknown-type"}, output="有点内容")
        self.assertEqual(kind, "assertion_failed")

    def test_invalid_rubric_and_not_scored_keep_their_verdict(self):
        self.assertEqual(classify_failure("invalid_rubric"), "invalid_rubric")
        self.assertEqual(classify_failure("not_scored"), "not_scored")


class DatasetCardTests(unittest.TestCase):
    def test_latest_run_is_attached_per_dataset(self):
        cards = dataset_cards(
            [{"dataset_id": "d1", "name": "A"}, {"dataset_id": "d2", "name": "B"}],
            [
                {"eval_run_id": "eval-1", "dataset_id": "d1", "status": "completed", "agent": "chat",
                 "epochs": 1, "created_at": "2026-11-23 09:00:00", "summary": {"passRate": 0.5}},
                {"eval_run_id": "eval-2", "dataset_id": "d1", "status": "completed", "agent": "chat",
                 "epochs": 2, "created_at": "2026-11-23 10:00:00", "summary": {"passRate": 1.0}},
            ],
        )
        self.assertEqual(cards[0]["lastRun"]["runId"], "eval-2")
        self.assertEqual(cards[0]["lastRun"]["passRate"], 1.0)
        self.assertEqual(cards[0]["lastRun"]["epochs"], 2)
        self.assertIsNone(cards[1]["lastRun"])

    def test_missing_summary_leaves_pass_rate_empty(self):
        cards = dataset_cards(
            [{"dataset_id": "d1", "name": "A"}],
            [{"eval_run_id": "eval-1", "dataset_id": "d1", "status": "running", "agent": "chat",
              "epochs": 1, "created_at": "2026-11-23 10:00:00"}],
        )
        self.assertIsNone(cards[0]["lastRun"]["passRate"])
        self.assertEqual(cards[0]["lastRun"]["status"], "running")
