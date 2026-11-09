from __future__ import annotations

import tempfile
import time
import unittest
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from ...api.routers.evaluation import create_evaluation_router, wait_for_background_runs
from ...api.routers.governance import create_governance_router
from ...api.routers.release import (
    create_release_router,
    run_release_observation_once,
    stop_release_observation,
)
from ...application.execution_service import WorkerUnavailableError
from ...infrastructure.evaluation_store import EvaluationStore
from ...infrastructure.governance_store import ApprovalStateError, GovernanceStore
from . import score_case


class FakeExecutionService:
    """Duck-typed stand-in for ExecutionApplicationService (no Worker, no DB)."""

    def __init__(self, outputs=None):
        self.outputs = outputs or {}
        self.created: list[tuple[str, object]] = []
        self.unavailable = False
        self.counter = 0

    def create(self, request):
        if self.unavailable:
            raise WorkerUnavailableError("Agent Execution Worker 未运行")
        self.counter += 1
        run_id = f"run-{self.counter}"
        self.created.append((run_id, request))
        return {"run_id": run_id, "status": "queued", "conversation_id": request.conversation_id}

    def get_run(self, run_id):
        for rid, request in self.created:
            if rid == run_id:
                return {"run_id": rid, "status": "completed", "error": None}
        return None

    def get_events(self, run_id, event_id=0):
        for rid, request in self.created:
            if rid == run_id:
                output = self.outputs.get(request.query, "")
                if not output:
                    return []
                return [{"event_id": 1, "event": {"type": "text", "content": output}}]
        return []


class FakeCatalog:
    def __init__(self):
        self.calls: list[tuple[str, dict]] = []
        self.rollouts: list[dict] = []
        self.metrics: list[dict] = []
        self.metric_result = {"ok": True, "autoRolledBack": False}

    def __call__(self, action, args):
        self.calls.append((action, args))
        if action == "rollouts":
            return {"rollouts": list(self.rollouts)}
        if action == "promote":
            return {"ok": True, "status": "active", "percentage": args.get("percentage", 10)}
        if action == "rollback":
            return {"ok": True, "version": "v1"}
        if action == "metric":
            return dict(self.metric_result)
        if action == "metrics":
            return {"metrics": list(self.metrics)}
        return {}

    def actions(self, action: str) -> list[dict]:
        return [args for name, args in self.calls if name == action]


class ScorerTests(unittest.TestCase):
    def test_rule_based_scoring_covers_every_supported_rubric(self):
        self.assertEqual(score_case("任意输出", "", {})["verdict"], "not_scored")
        self.assertEqual(score_case("包含答案", "答案", {})["verdict"], "passed")
        self.assertEqual(score_case("别的内容", "答案", {})["verdict"], "failed")
        self.assertEqual(score_case("前缀答案后缀", "", {"type": "contains", "value": "答案"})["verdict"], "passed")
        self.assertEqual(score_case("答案", "", {"type": "equals", "value": " 答案 "})["verdict"], "passed")
        self.assertEqual(score_case("答案", "", {"type": "equals", "value": "其他"})["verdict"], "failed")
        self.assertEqual(score_case('{"a": 1}', "", {"type": "json_equals", "value": {"a": 1}})["verdict"], "passed")
        self.assertEqual(score_case('{"a": 2}', "", {"type": "json_equals", "value": {"a": 1}})["verdict"], "failed")
        self.assertEqual(score_case("不是 JSON", "", {"type": "json_equals", "value": "不是 JSON"})["verdict"], "passed")
        self.assertEqual(score_case("任意输出", "", {"type": "always"})["verdict"], "passed")
        self.assertEqual(score_case("任意输出", "", {"type": "unknown"})["verdict"], "invalid_rubric")
        self.assertEqual(score_case("任意输出", "", {"type": "contains"})["verdict"], "invalid_rubric")


class EvaluationStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.store = EvaluationStore(self.root / "evaluation.db")

    def tearDown(self):
        self.temp.cleanup()

    def test_delete_dataset_removes_cases_and_reports_missing(self):
        dataset = self.store.create_dataset("集", "通用")
        self.store.add_case(dataset["dataset_id"], "问题")
        self.assertTrue(self.store.delete_dataset(dataset["dataset_id"]))
        self.assertIsNone(self.store.get_dataset(dataset["dataset_id"]))
        self.assertFalse(self.store.delete_dataset(dataset["dataset_id"]))

    def test_snapshot_increments_version_but_case_edit_does_not(self):
        dataset = self.store.create_dataset("集", "通用")
        dataset_id = dataset["dataset_id"]
        case = self.store.add_case(dataset_id, "问题")
        self.store.update_case(dataset_id, case["case_id"], "新问题", "", {})
        self.assertEqual(self.store.get_dataset(dataset_id)["version"], 1)
        snapshot = self.store.create_snapshot(dataset_id)
        self.assertEqual(snapshot["version"], 1)
        self.assertEqual(snapshot["payload"]["case_count"], 1)
        self.assertEqual(self.store.get_dataset(dataset_id)["version"], 2)
        self.assertEqual(len(self.store.list_snapshots(dataset_id)), 1)

    def test_batch_import_is_atomic(self):
        dataset = self.store.create_dataset("集", "通用")
        dataset_id = dataset["dataset_id"]
        created = self.store.add_cases(dataset_id, [{"input": "a"}, {"input": "b"}])
        self.assertEqual(len(created), 2)
        self.assertEqual(self.store.get_dataset(dataset_id)["case_count"], 2)


class EvaluationRouterTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.store = EvaluationStore(self.root / "evaluation.db")
        self.service = FakeExecutionService({"问一": "答一"})

    def tearDown(self):
        # 后台测评线程可能还持有 SQLite 句柄，先等它们结束再删临时目录。
        wait_for_background_runs()
        self.temp.cleanup()

    def client(self, service=None):
        app = FastAPI()
        app.include_router(create_evaluation_router(self.store, service or self.service))
        return TestClient(app)

    def wait_for_run(self, client, eval_run_id, timeout=15.0):
        """测评在后台线程执行，测试轮询到终态再断言。"""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            body = client.get(f"/evaluation/runs/{eval_run_id}").json()
            if body["run"]["status"] not in {"running", "queued"}:
                return body
            time.sleep(0.05)
        self.fail("测评运行未在超时前到达终态")

    def dataset(self):
        response = self.client().post("/evaluation/datasets", json={"name": "集", "datasetType": "通用"})
        return response.json()["dataset"]["dataset_id"]

    def test_dataset_delete_and_batch_import(self):
        client = self.client()
        dataset_id = self.dataset()
        empty = client.post(f"/evaluation/datasets/{dataset_id}/cases/batch", json={"cases": [{"input": "  "}]})
        self.assertEqual(empty.status_code, 400)
        self.assertEqual(self.store.get_dataset(dataset_id)["case_count"], 0)
        too_many = client.post(f"/evaluation/datasets/{dataset_id}/cases/batch",
                               json={"cases": [{"input": "x"} for _ in range(501)]})
        self.assertEqual(too_many.status_code, 400)
        created = client.post(f"/evaluation/datasets/{dataset_id}/cases/batch",
                              json={"cases": [{"input": "a"}, {"input": "b"}]})
        self.assertEqual(created.status_code, 200)
        self.assertEqual(created.json()["created"], 2)
        self.assertEqual(client.delete(f"/evaluation/datasets/{dataset_id}").json(), {"success": True})
        self.assertEqual(client.delete(f"/evaluation/datasets/{dataset_id}").status_code, 404)

    def test_snapshot_endpoint_creates_version(self):
        client = self.client()
        dataset_id = self.dataset()
        client.post(f"/evaluation/datasets/{dataset_id}/cases", json={"input": "问题"})
        response = client.post(f"/evaluation/datasets/{dataset_id}/snapshots")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["snapshot"]["version"], 1)
        self.assertEqual(len(client.get(f"/evaluation/datasets/{dataset_id}/snapshots").json()["items"]), 1)
        self.assertEqual(client.get(f"/evaluation/datasets/{dataset_id}").json()["dataset"]["version"], 2)

    def test_run_executes_cases_and_scores_them(self):
        client = self.client()
        dataset_id = self.dataset()
        client.post(f"/evaluation/datasets/{dataset_id}/cases", json={"input": "问一", "expectedOutput": "答一"})
        client.post(f"/evaluation/datasets/{dataset_id}/cases", json={"input": "问二", "expectedOutput": "答二"})
        response = client.post("/evaluation/runs", json={"datasetId": dataset_id, "agent": "chat"})
        self.assertEqual(response.status_code, 200)
        body = self.wait_for_run(client, response.json()["run"]["eval_run_id"])
        self.assertEqual(body["run"]["status"], "completed")
        self.assertEqual(body["run"]["summary"]["passedCount"], 1)
        self.assertEqual(body["run"]["summary"]["caseCount"], 2)
        self.assertEqual(body["run"]["summary"]["passRate"], 0.5)
        self.assertEqual(sorted(item["verdict"] for item in body["results"]), ["failed", "passed"])
        detail = client.get(f"/evaluation/runs/{body['run']['eval_run_id']}").json()
        self.assertEqual(len(detail["results"]), 2)

    def test_run_is_blocked_without_worker_or_samples(self):
        client = self.client()
        dataset_id = self.dataset()
        blocked = client.post("/evaluation/runs", json={"datasetId": dataset_id}).json()
        self.assertEqual(blocked["run"]["status"], "blocked")
        self.assertIn("没有样本", blocked["run"]["error"])

        client.post(f"/evaluation/datasets/{dataset_id}/cases", json={"input": "问一", "expectedOutput": "答一"})
        self.service.unavailable = True
        started = client.post("/evaluation/runs", json={"datasetId": dataset_id}).json()
        blocked = self.wait_for_run(client, started["run"]["eval_run_id"])
        self.assertEqual(blocked["run"]["status"], "blocked")
        self.assertIn("执行服务不可用", blocked["run"]["error"])
        self.assertEqual(blocked["results"], [])

    def test_replay_only_replays_failed_samples(self):
        client = self.client()
        dataset_id = self.dataset()
        client.post(f"/evaluation/datasets/{dataset_id}/cases", json={"input": "问一", "expectedOutput": "答一"})
        client.post(f"/evaluation/datasets/{dataset_id}/cases", json={"input": "问二", "expectedOutput": "答二"})
        started = client.post("/evaluation/runs", json={"datasetId": dataset_id}).json()["run"]
        run = self.wait_for_run(client, started["eval_run_id"])["run"]
        replay = client.post(f"/evaluation/runs/{run['eval_run_id']}/replay", json={}).json()
        self.assertEqual(len(replay["runs"]), 1)
        self.assertEqual(replay["runs"][0]["status"], "queued")
        kept = client.get(f"/evaluation/runs/{run['eval_run_id']}").json()["results"]
        self.assertEqual(len(kept), 2)

        clean = self.client()
        other = self.dataset()
        clean.post(f"/evaluation/datasets/{other}/cases", json={"input": "问一", "expectedOutput": "答一"})
        passed_run = clean.post("/evaluation/runs", json={"datasetId": other}).json()["run"]
        self.assertEqual(clean.post(f"/evaluation/runs/{passed_run['eval_run_id']}/replay", json={}).json(), {"runs": []})


class GovernanceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.store = GovernanceStore(self.root / "governance.db")
        self.app = FastAPI()
        self.app.include_router(create_governance_router(lambda: [], self.store))
        self.client = TestClient(self.app)

    def tearDown(self):
        self.temp.cleanup()

    def create(self, **payload):
        body = {"runId": "run-1", "tool": "delete_file"}
        body.update(payload)
        return self.client.post("/harness/approvals", json=body).json()["approval"]

    def test_deciding_twice_returns_conflict(self):
        approval = self.create()
        first = self.client.post(f"/harness/approvals/{approval['request_id']}/decision",
                                 json={"decision": "approved", "reason": "可以"})
        self.assertEqual(first.status_code, 200)
        second = self.client.post(f"/harness/approvals/{approval['request_id']}/decision",
                                  json={"decision": "rejected"})
        self.assertEqual(second.status_code, 409)
        self.assertIn("已决定", second.json()["detail"])
        with self.assertRaises(ApprovalStateError):
            self.store.decide(approval["request_id"], "approved")

    def test_expired_approvals_are_marked_and_cannot_be_decided(self):
        approval = self.create(timeoutSeconds=60)
        self.assertTrue(approval["expires_at"])
        with self.store._db() as db:
            db.execute("UPDATE harness_approval SET expires_at='2020-01-01T00:00:00Z' WHERE request_id=?",
                       (approval["request_id"],))
        items = self.client.get("/harness/approvals").json()["items"]
        self.assertEqual(items[0]["status"], "expired")
        self.assertEqual(self.client.get(f"/harness/approvals/{approval['request_id']}").json()["approval"]["status"], "expired")
        decision = self.client.post(f"/harness/approvals/{approval['request_id']}/decision",
                                    json={"decision": "approved"})
        self.assertEqual(decision.status_code, 409)

    def test_batch_decide_keeps_failures_isolated(self):
        first = self.create()
        second = self.create()
        self.client.post(f"/harness/approvals/{first['request_id']}/decision", json={"decision": "approved"})
        response = self.client.post("/harness/approvals/decide-batch",
                                    json={"requestIds": [first["request_id"], second["request_id"], "missing"],
                                          "decision": "rejected", "reason": "不允许"})
        body = response.json()
        self.assertEqual(len(body["items"]), 1)
        self.assertEqual(body["items"][0]["request_id"], second["request_id"])
        self.assertEqual(body["items"][0]["operator"], "harness-operator")
        self.assertEqual({item["requestId"] for item in body["failed"]}, {first["request_id"], "missing"})

    def test_audit_export_is_csv_with_bom(self):
        approval = self.create(risk="medium", detail="删除文件")
        self.client.post(f"/harness/approvals/{approval['request_id']}/decision",
                         json={"decision": "approved", "reason": "可以", "operator": "alice"})
        response = self.client.get("/harness/approvals/audit")
        self.assertEqual(response.headers["content-type"].split(";")[0], "text/csv")
        self.assertTrue(response.content.startswith(b"\xef\xbb\xbf"))
        text = response.content.decode("utf-8-sig")
        self.assertIn("request_id,run_id,tool,risk,status,reason,operator,created_at,decided_at", text)
        self.assertIn("alice", text)


class ReleaseTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.store = GovernanceStore(self.root / "governance.db")
        self.catalog = FakeCatalog()
        self.app = FastAPI()
        self.app.include_router(create_release_router(
            self.catalog, "demo", lambda run_id: {"eval_run_id": run_id} if run_id else None, self.store))
        self.client = TestClient(self.app)

    def tearDown(self):
        # 后台观察线程会碰治理库句柄，删临时目录前先停掉。
        stop_release_observation()
        self.temp.cleanup()

    def test_gate_persists_eval_run_id(self):
        response = self.client.post("/release/gate", json={
            "e2ePassRate": 0.95, "ragFaithfulness": 0.9, "highRiskErrors": 0,
            "evalRunId": "eval-1", "project": "demo", "name": "skill", "version": "v2",
        })
        self.assertEqual(response.status_code, 200)
        gate = response.json()["gate"]
        self.assertEqual(gate["eval_run_id"], "eval-1")
        self.assertEqual(self.store.list_gates()[0]["eval_run_id"], "eval-1")

    def test_gate_thresholds_are_configurable(self):
        failing = self.client.post("/release/gate", json={
            "e2ePassRate": 0.6, "ragFaithfulness": 0.6, "highRiskErrors": 1})
        self.assertFalse(failing.json()["passed"])
        saved = self.client.put("/release/gate-thresholds", json={
            "e2ePassRate": 0.5, "ragFaithfulness": 0.5, "highRiskErrors": 2})
        self.assertEqual(saved.status_code, 200)
        passing = self.client.post("/release/gate", json={
            "e2ePassRate": 0.6, "ragFaithfulness": 0.6, "highRiskErrors": 1})
        self.assertTrue(passing.json()["passed"])

    def test_release_config_round_trip(self):
        response = self.client.put("/release/config", json={
            "rolloutErrorThreshold": 0.2, "rolloutMinSamples": 5, "autoRollback": False})
        self.assertEqual(response.status_code, 200)
        config = self.client.get("/release/config").json()["config"]
        self.assertEqual(config["rolloutErrorThreshold"], 0.2)
        self.assertEqual(config["rolloutMinSamples"], 5)
        self.assertFalse(config["autoRollback"])

    def test_promote_writes_record_with_gate_evidence(self):
        gate = self.client.post("/release/gate", json={
            "e2ePassRate": 0.95, "ragFaithfulness": 0.9, "highRiskErrors": 0,
            "evalRunId": "eval-1", "project": "demo", "name": "skill", "version": "v2"}).json()["gate"]
        promoted = self.client.post("/release/promote", json={
            "project": "demo", "name": "skill", "version": "v2", "percentage": 20,
            "gate": {"gate_id": gate["gate_id"]}, "operator": "alice"})
        self.assertEqual(promoted.status_code, 200)
        records = self.client.get("/release/records").json()["items"]
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["action"], "promote")
        self.assertEqual(records[0]["gate_id"], gate["gate_id"])
        self.assertEqual(records[0]["eval_run_id"], "eval-1")
        self.assertEqual(records[0]["actor"], "alice")
        self.assertTrue(records[0]["checks"]["e2ePassRate"])
        self.assertEqual(records[0]["thresholds"]["e2ePassRate"], 0.9)

    def test_promote_without_passing_gate_is_rejected(self):
        response = self.client.post("/release/promote", json={
            "project": "demo", "name": "skill", "version": "v2", "percentage": 20,
            "gate": {"e2ePassRate": 0.1, "ragFaithfulness": 0.1, "highRiskErrors": 3}})
        self.assertEqual(response.status_code, 412)
        self.assertEqual(self.client.get("/release/records").json()["items"], [])

    def test_advance_requires_monotonic_percentage(self):
        self.catalog.rollouts = [{"project": "demo", "name": "skill", "candidate_version": "v3",
                                  "previous_version": "v2", "percentage": 30, "active": 1}]
        rejected = self.client.post("/release/rollouts/advance",
                                    json={"project": "demo", "name": "skill", "percentage": 20})
        self.assertEqual(rejected.status_code, 400)
        advanced = self.client.post("/release/rollouts/advance",
                                    json={"project": "demo", "name": "skill", "percentage": 60})
        self.assertEqual(advanced.status_code, 200)
        records = self.client.get("/release/records").json()["items"]
        self.assertEqual(records[0]["action"], "advance")
        self.assertEqual(records[0]["percentage"], 60)
        self.assertEqual(records[0]["version"], "v3")

    def test_metric_auto_rollback_is_recorded(self):
        self.catalog.metric_result = {"ok": True, "autoRolledBack": True}
        response = self.client.post("/release/metrics", json={
            "project": "demo", "name": "skill", "version": "v3", "metric": "error_rate", "value": 0.5})
        self.assertEqual(response.status_code, 200)
        records = self.client.get("/release/records").json()["items"]
        self.assertEqual(records[0]["action"], "auto_rollback")

    def test_rollback_writes_record(self):
        response = self.client.post("/release/rollback", json={"project": "demo", "name": "skill"})
        self.assertEqual(response.status_code, 200)
        records = self.client.get("/release/records").json()["items"]
        self.assertEqual(records[0]["action"], "rollback")


class ModelScoringTests(unittest.TestCase):
    """模型评分：没有模型配置时必须如实报 scorer_unavailable，不能伪造分数。"""

    def setUp(self):
        from ... import config as config_module
        self.config_module = config_module
        self._original = config_module.settings

    def tearDown(self):
        self.config_module.settings = self._original

    def blank_settings(self):
        blank = self._original.__class__(
            model_api_key="", model_name="", model_base_url="")
        self.config_module.settings = blank

    def test_model_rubric_without_model_config_is_scorer_unavailable(self):
        self.blank_settings()
        result = score_case("任意输出", "期望输出", {"type": "model", "prompt": "判断是否正确"})
        self.assertEqual(result["verdict"], "scorer_unavailable")
        self.assertEqual(result["score"], 0.0)
        self.assertIn("模型评分不可用", result["detail"])

    def test_model_rubric_uses_injected_model_output(self):
        def scorer(rubric, actual, expected):
            return '{"score": 0.8, "verdict": "passed", "reason": "满足要求"}'
        result = score_case("任意输出", "期望输出", {"type": "model"}, model_scorer=scorer)
        self.assertEqual(result["verdict"], "passed")
        self.assertEqual(result["score"], 0.8)
        self.assertEqual(result["detail"], "满足要求")

    def test_model_rubric_with_unparsable_output_is_scorer_unavailable(self):
        def scorer(rubric, actual, expected):
            return "这不是 JSON"
        result = score_case("任意输出", "期望输出", {"type": "model"}, model_scorer=scorer)
        self.assertEqual(result["verdict"], "scorer_unavailable")
        self.assertEqual(result["score"], 0.0)

    def test_rule_rubrics_behave_the_same_without_model_type(self):
        self.blank_settings()
        self.assertEqual(score_case("包含答案", "答案", {"type": "contains", "value": "答案"})["verdict"], "passed")
        self.assertEqual(score_case("别的内容", "答案", {"type": "equals", "value": "答案"})["verdict"], "failed")
        self.assertEqual(score_case("任意输出", "", {"type": "unknown"})["verdict"], "invalid_rubric")


class EvaluationCompareAndExportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.store = EvaluationStore(self.root / "evaluation.db")
        self.app = FastAPI()
        self.app.include_router(create_evaluation_router(self.store, FakeExecutionService({})))
        self.client = TestClient(self.app)

    def tearDown(self):
        wait_for_background_runs()
        self.temp.cleanup()

    def make_run(self, dataset_id, results, summary=None):
        run = self.store.create_run(dataset_id, "chat", "v1", status="completed")
        for case_id, verdict, score in results:
            self.store.save_result(run["eval_run_id"], case_id, score, verdict, "详情", "输出")
        self.store.update_run(run["eval_run_id"], "completed", summary=summary or {
            "caseCount": len(results),
            "passedCount": sum(1 for item in results if item[1] == "passed"),
            "failedCount": sum(1 for item in results if item[1] != "passed"),
            "passRate": round(sum(1 for item in results if item[1] == "passed") / len(results), 4),
        })
        return run["eval_run_id"]

    def test_compare_reports_improved_regressed_added_removed(self):
        dataset = self.store.create_dataset("集", "通用")
        dataset_id = dataset["dataset_id"]
        base = self.make_run(dataset_id, [("c1", "failed", 0.0), ("c2", "passed", 1.0), ("c3", "passed", 1.0)])
        target = self.make_run(dataset_id, [("c1", "passed", 1.0), ("c2", "failed", 0.0), ("c4", "passed", 1.0)])
        body = self.client.get("/evaluation/runs/compare", params={"base": base, "target": target}).json()
        self.assertTrue(body["sameDataset"])
        self.assertEqual(body["summaryDiff"]["passedCount"]["base"], 2)
        self.assertEqual(body["summaryDiff"]["passedCount"]["target"], 2)
        self.assertEqual(body["summaryDiff"]["passedCount"]["delta"], 0)
        changes = {item["caseId"]: item["change"] for item in body["cases"]}
        self.assertEqual(changes, {"c1": "improved", "c2": "regressed", "c3": "removed", "c4": "added"})
        improved = next(item for item in body["cases"] if item["caseId"] == "c1")
        self.assertEqual(improved["base"]["verdict"], "failed")
        self.assertEqual(improved["target"]["verdict"], "passed")

    def test_compare_flags_different_datasets(self):
        first = self.store.create_dataset("集一", "通用")
        second = self.store.create_dataset("集二", "通用")
        base = self.make_run(first["dataset_id"], [("c1", "passed", 1.0)])
        target = self.make_run(second["dataset_id"], [("c1", "passed", 1.0)])
        body = self.client.get("/evaluation/runs/compare", params={"base": base, "target": target}).json()
        self.assertFalse(body["sameDataset"])

    def test_compare_missing_run_returns_404(self):
        dataset = self.store.create_dataset("集", "通用")
        run = self.make_run(dataset["dataset_id"], [("c1", "passed", 1.0)])
        missing_base = self.client.get("/evaluation/runs/compare", params={"base": "eval-none", "target": run})
        self.assertEqual(missing_base.status_code, 404)
        self.assertIn("基线", missing_base.json()["detail"])
        missing_target = self.client.get("/evaluation/runs/compare", params={"base": run, "target": "eval-none"})
        self.assertEqual(missing_target.status_code, 404)
        self.assertIn("对比", missing_target.json()["detail"])

    def test_export_json_and_csv(self):
        dataset = self.store.create_dataset("集", "通用")
        run = self.make_run(dataset["dataset_id"], [("c1", "passed", 1.0), ("c2", "failed", 0.0)])
        body = self.client.get(f"/evaluation/runs/{run}/export", params={"format": "json"}).json()
        self.assertEqual(body["run"]["eval_run_id"], run)
        self.assertEqual(len(body["results"]), 2)
        response = self.client.get(f"/evaluation/runs/{run}/export", params={"format": "csv"})
        self.assertEqual(response.headers["content-type"].split(";")[0], "text/csv")
        lines = response.text.strip().splitlines()
        self.assertTrue(lines[0].lstrip("\ufeff").startswith("case_id,score,verdict,detail,actual_output,created_at"))
        self.assertIn("c1", lines[1])
        self.assertIn("c2", lines[2])

    def test_export_missing_run_returns_404(self):
        self.assertEqual(self.client.get("/evaluation/runs/eval-none/export").status_code, 404)


class RolloutObservationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.store = GovernanceStore(self.root / "governance.db")
        self.catalog = FakeCatalog()
        self.catalog.rollouts = [{
            "project": "demo", "name": "skill", "candidate_version": "v2",
            "previous_version": "v1", "percentage": 20, "active": 1,
        }]
        self.app = FastAPI()
        self.app.include_router(create_release_router(
            self.catalog, "demo", lambda run_id: None, self.store))
        self.client = TestClient(self.app)
        self.client.put("/release/config", json={
            "rolloutErrorThreshold": 0.2, "rolloutMinSamples": 2, "autoRollback": True})

    def tearDown(self):
        stop_release_observation()
        self.temp.cleanup()

    def add_metrics(self, values):
        self.catalog.metrics = [
            {"project": "demo", "name": "skill", "version": "v2", "metric": "error_rate", "value": value}
            for value in values
        ]

    def test_observation_with_not_enough_samples_does_not_rollback(self):
        self.add_metrics([0.5])
        body = self.client.post("/release/rollouts/observe", json={"name": "skill"}).json()
        self.assertFalse(body["rolledBack"])
        self.assertEqual(body["sampleCount"], 1)
        self.assertIn("样本不足", body["detail"])
        self.assertEqual(body["observation"]["auto_rolled_back"], 0)
        self.assertEqual(self.catalog.actions("rollback"), [])

    def test_observation_over_threshold_triggers_auto_rollback_with_details(self):
        self.add_metrics([0.4, 0.6])
        body = self.client.post("/release/rollouts/observe", json={"name": "skill"}).json()
        self.assertTrue(body["rolledBack"])
        self.assertEqual(len(self.catalog.actions("rollback")), 1)
        self.assertEqual(body["observation"]["auto_rolled_back"], 1)
        self.assertAlmostEqual(body["observation"]["error_rate"], 0.5)
        self.assertEqual(body["observation"]["sample_count"], 2)
        self.assertAlmostEqual(body["observation"]["threshold"], 0.2)
        records = self.client.get("/release/records").json()["items"]
        auto = next(item for item in records if item["action"] == "auto_rollback")
        self.assertAlmostEqual(auto["error_rate"], 0.5)
        self.assertEqual(auto["sample_count"], 2)
        self.assertAlmostEqual(auto["threshold"], 0.2)

    def test_observation_without_auto_rollback_records_but_keeps_rollout(self):
        self.client.put("/release/config", json={
            "rolloutErrorThreshold": 0.2, "rolloutMinSamples": 2, "autoRollback": False})
        self.add_metrics([0.9, 0.9])
        body = self.client.post("/release/rollouts/observe", json={"name": "skill"}).json()
        self.assertFalse(body["rolledBack"])
        self.assertIn("未开启自动回滚", body["detail"])
        self.assertEqual(self.catalog.actions("rollback"), [])
        self.assertEqual(len(self.client.get("/release/observations").json()["items"]), 1)

    def test_observation_of_unknown_rollout_returns_404(self):
        response = self.client.post("/release/rollouts/observe", json={"name": "missing"})
        self.assertEqual(response.status_code, 404)

    def test_scheduled_observation_covers_active_rollouts_and_survives_failures(self):
        self.add_metrics([0.9, 0.9])
        run_release_observation_once()
        self.assertEqual(len(self.catalog.actions("rollback")), 1)
        # 单个灰度失败不能影响其它灰度，也不能让观察线程退出。
        self.catalog.rollouts.append({
            "project": "demo", "name": "broken", "candidate_version": "v2",
            "percentage": 10, "active": 1})
        run_release_observation_once()
        self.assertEqual(len(self.catalog.actions("rollback")), 2)

    def test_auto_rollback_record_keeps_error_snapshot(self):
        self.catalog.metric_result = {"ok": True, "autoRolledBack": True}
        self.add_metrics([0.5, 0.7])
        self.client.post("/release/metrics", json={
            "project": "demo", "name": "skill", "version": "v2", "metric": "error_rate", "value": 0.5})
        records = self.client.get("/release/records").json()["items"]
        auto = records[0]
        self.assertEqual(auto["action"], "auto_rollback")
        self.assertAlmostEqual(auto["error_rate"], 0.6)
        self.assertEqual(auto["sample_count"], 2)
        self.assertAlmostEqual(auto["threshold"], 0.2)


if __name__ == "__main__":
    unittest.main()
