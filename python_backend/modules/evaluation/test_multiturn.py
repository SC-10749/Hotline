"""多轮评测、用户模拟器、门禁 CLI，以及会话列表的测评隔离。

对应规格 S-003。先写期望，再改实现。
"""
from __future__ import annotations

import tempfile
import time
import unittest
from dataclasses import replace
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from ...api.routers.evaluation import create_evaluation_router
from ...config import Settings
from ...infrastructure.evaluation_store import EvaluationStore
from ...modules.storage.relational import Storage
from . import score_case
from .simulator import END_MARKER, next_user_message


class TurnService:
    """按（会话编号, 第几轮）返回事件，用来验证多轮确实发生。"""

    def __init__(self, responder=None):
        self.responder = responder or (lambda conversation_id, index: [{"type": "text", "content": "ok"}])
        self.index = {}
        self.by_run = {}
        self.calls = []

    def create(self, request):
        seen = self.index.get(request.conversation_id, 0)
        self.index[request.conversation_id] = seen + 1
        run_id = f"run-{len(self.by_run) + 1}"
        self.by_run[run_id] = (request.conversation_id, seen)
        return {"run_id": run_id, "status": "queued", "conversation_id": request.conversation_id}

    def get_run(self, run_id):
        if run_id not in self.by_run:
            return None
        return {"run_id": run_id, "status": "completed", "error": None}

    def get_events(self, run_id, event_id=0):
        conversation_id, seen = self.by_run[run_id]
        self.calls.append((conversation_id, seen))
        events = self.responder(conversation_id, seen)
        return [{"event_id": index + 1, "event": event} for index, event in enumerate(events)]


class SimulatorTests(unittest.TestCase):
    def test_end_marker_ends_the_conversation(self):
        self.assertEqual(next_user_message("画像", [], simulator=lambda profile, dialogue: END_MARKER), "")

    def test_normal_reply_is_kept(self):
        self.assertEqual(
            next_user_message("画像", [], simulator=lambda profile, dialogue: "  再补充一下  "), "再补充一下")

    def test_empty_reply_ends_the_conversation(self):
        self.assertEqual(next_user_message("画像", [], simulator=lambda profile, dialogue: ""), "")


class MultiTurnRunTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.store = EvaluationStore(root / "evaluation.db")
        self.service = TurnService()
        self.simulator = None
        self.client = self.build_client()
        dataset = self.client.post("/evaluation/datasets", json={
            "name": "多轮需求澄清", "datasetType": "需求"}).json()["dataset"]
        self.dataset_id = dataset["dataset_id"]

    def build_client(self):
        app = FastAPI()
        app.include_router(create_evaluation_router(self.store, self.service, user_simulator=self.simulator))
        return TestClient(app)

    def add_case(self, **extra):
        payload = {"input": "我要一个客服系统", "expectedOutput": "", "rubric": {"type": "always"}}
        payload.update(extra)
        return self.client.post(f"/evaluation/datasets/{self.dataset_id}/cases", json=payload).json()["case"]

    def run_evaluation(self, epochs=1):
        response = self.client.post("/evaluation/runs", json={
            "datasetId": self.dataset_id, "agent": "chat", "epochs": epochs})
        self.assertEqual(response.status_code, 200)
        run_id = response.json()["run"]["eval_run_id"]
        for _ in range(100):
            detail = self.client.get(f"/evaluation/runs/{run_id}").json()
            if detail["run"]["status"] in {"completed", "failed", "blocked", "cancelled"}:
                return detail
            time.sleep(0.05)
        self.fail("测评未在预期时间内结束")

    def test_scripted_turns_run_in_one_conversation(self):
        self.add_case(turns=["补充：只做移动端", "再补充：要有工单导出"])
        self.service.responder = lambda conversation_id, index: [
            {"type": "text", "content": f"回答{index}"},
            {"type": "clarify", "content": "请补充"}]

        detail = self.run_evaluation()
        result = detail["results"][0]

        self.assertEqual(result["trace"]["turns"], 3)
        self.assertEqual(result["trace"]["transcript"], ["回答0", "回答1", "回答2"])
        self.assertEqual(result["actual_output"], "回答2")
        self.assertEqual(len({cid for cid, _ in self.service.calls}), 1)
        self.assertEqual(sorted({index for _, index in self.service.calls}), [0, 1, 2])
        self.assertEqual(detail["run"]["summary"]["avgTurns"], 3)

    def test_clarify_turn_is_recorded_in_transcript(self):
        self.add_case()
        self.service.responder = lambda conversation_id, index: [
            {"type": "clarify", "content": {"question": "给谁用？", "options": [{"label": "客服人员"}]}}]

        detail = self.run_evaluation()

        transcript = detail["results"][0]["trace"]["transcript"]
        self.assertEqual(len(transcript), 1)
        self.assertIn("【需要澄清】", transcript[0])
        self.assertIn("给谁用？", transcript[0])

    def test_single_turn_case_stays_single_turn(self):
        self.add_case()
        detail = self.run_evaluation()
        self.assertEqual(detail["results"][0]["trace"]["turns"], 1)
        self.assertEqual(detail["run"]["summary"]["avgTurns"], 1)

    def test_simulated_user_drives_the_extra_turns(self):
        self.add_case(userProfile="只想做移动端")
        replies = iter(["还要能导出工单", ""])

        def simulator(profile, dialogue):
            self.assertEqual(profile, "只想做移动端")
            return next(replies, "")

        self.simulator = simulator
        self.client = self.build_client()
        detail = self.run_evaluation()
        result = detail["results"][0]

        self.assertEqual(result["trace"]["turns"], 2)
        self.assertEqual(len(result["trace"]["transcript"]), 2)

    def test_trace_rule_can_assert_turn_count(self):
        trace = {"agent": "chat", "counts": {"turns": 3, "clarify": 1}, "tools": [], "tokens": 1, "latencyMs": 1}
        passed = score_case("x", "", {"type": "trace", "expect": {"minTurns": 2, "maxTurns": 4}}, trace=trace)
        self.assertEqual(passed["verdict"], "passed")
        failed = score_case("x", "", {"type": "trace", "expect": {"minTurns": 5}}, trace=trace)
        self.assertEqual(failed["verdict"], "failed")
        self.assertIn("轮数", failed["detail"])

    def test_case_stores_turns_and_profile(self):
        case = self.add_case(turns=["第二轮"], userProfile="只想做移动端")
        stored = self.client.get(f"/evaluation/datasets/{self.dataset_id}").json()["dataset"]["cases"][0]
        self.assertEqual(stored["turns"], ["第二轮"])
        self.assertEqual(stored["user_profile"], "只想做移动端")
        self.assertEqual(case["turns"], ["第二轮"])


class EvalSessionIsolationTests(unittest.TestCase):
    def test_eval_conversations_do_not_show_in_session_list(self):
        with tempfile.TemporaryDirectory(prefix="eval-session-") as temp:
            config = replace(Settings(), data_dir=Path(temp), storage_backend="sqlite", redis_enabled=False,
                             vector_enabled=False, file_storage_backend="local", model_api_key="")
            storage = Storage(config)
            row = storage.save_question("eval:run-1:case-1:0", "我要一个客服系统", "chat", None)
            storage.update_answer(row, "需求条目")
            normal = storage.save_question("real-1", "真实会话", "chat", None)
            storage.update_answer(normal, "回答")

            rows, total = storage.session_list(0, 10)

            self.assertEqual([row.conversationId for row in rows], ["real-1"])
            self.assertEqual(total, 1)


class GateCliTests(unittest.TestCase):
    def test_cli_exits_nonzero_when_gate_fails(self):
        from ... import eval_gate
        with tempfile.TemporaryDirectory(prefix="eval-gate-") as temp:
            db_path = Path(temp) / "evaluation.db"
            store = EvaluationStore(db_path)
            dataset = store.create_dataset("集", "通用")
            case = store.add_case(dataset["dataset_id"], "问题")
            run = store.create_run(dataset["dataset_id"], "chat", "", status="completed")
            store.save_result(run["eval_run_id"], case["case_id"], 1.0, "passed", "", "输出")
            store.update_run(run["eval_run_id"], "completed", summary={
                "caseCount": 1, "resultCount": 1, "passedCount": 1, "failedCount": 0,
                "passRate": 0.5, "epochs": 1, "passAtK": 0.5, "flakyRate": 0.0,
                "avgLatencyMs": 10.0, "avgTokens": 5.0, "failureKinds": {}})
            store.save_config({"dimensions": [], "gates": [
                {"label": "通过率", "metric": "passRate", "op": ">=", "value": 0.9}]})

            code = eval_gate.main(["--target", run["eval_run_id"], "--db", str(db_path)])

            self.assertEqual(code, 1)


if __name__ == "__main__":
    unittest.main()
