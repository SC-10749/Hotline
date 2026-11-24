"""定时任务（安排任务）的存储、接口与调度测试。"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from ...api.routers.schedules import create_schedule_runner, create_schedules_router
from ...infrastructure.scheduled_store import ScheduledStore


class StubService:
    """只实现调度需要的 create；没有可用 Worker 时抛错。"""

    def __init__(self, fail: bool = False):
        self.requests = []
        self.fail = fail

    def create(self, request):
        if self.fail:
            raise RuntimeError("Agent Execution Worker 未运行")
        self.requests.append(request)
        return {"run_id": "run-stub", "status": "queued"}


class ScheduleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = ScheduledStore(Path(self.temp.name) / "schedules.db")
        self.service = StubService()
        app = FastAPI()
        app.include_router(create_schedules_router(self.store, self.service))
        self.client = TestClient(app)

    def tearDown(self):
        self.temp.cleanup()

    def test_task_crud_round_trip(self):
        created = self.client.post("/harness/schedules", json={
            "name": "每日巡检", "prompt": "检查服务状态", "intervalMinutes": 30,
        })
        self.assertEqual(created.status_code, 200)
        task = created.json()["task"]
        self.assertEqual(task["name"], "每日巡检")
        self.assertEqual(task["interval_minutes"], 30)
        self.assertEqual(self.client.get("/harness/schedules").json()["items"][0]["task_id"], task["task_id"])

        updated = self.client.put(f"/harness/schedules/{task['task_id']}", json={"enabled": False, "intervalMinutes": 15})
        self.assertEqual(updated.status_code, 200)
        self.assertEqual(updated.json()["task"]["interval_minutes"], 15)
        self.assertEqual(updated.json()["task"]["enabled"], 0)

        self.assertEqual(self.client.delete(f"/harness/schedules/{task['task_id']}").status_code, 200)
        self.assertEqual(self.client.get("/harness/schedules").json()["items"], [])

    def test_run_now_submits_execution(self):
        task = self.store.create({"name": "巡检", "prompt": "检查状态", "interval_minutes": 60})
        response = self.client.post(f"/harness/schedules/{task['task_id']}/run")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(self.service.requests), 1)
        self.assertEqual(self.service.requests[0].query, "检查状态")
        self.assertTrue(self.store.get(task["task_id"])["last_run_at"])

    def test_run_now_reports_unavailable_worker(self):
        self.service.fail = True
        task = self.store.create({"name": "巡检", "prompt": "检查状态", "interval_minutes": 60})
        response = self.client.post(f"/harness/schedules/{task['task_id']}/run")
        self.assertEqual(response.status_code, 503)

    def test_runner_only_runs_due_tasks(self):
        task = self.store.create({"name": "巡检", "prompt": "检查状态", "interval_minutes": 60})
        runner = create_schedule_runner(self.store, self.service)
        runner()
        runner()
        self.assertEqual(len(self.service.requests), 1)
        self.assertEqual(self.store.get(task["task_id"])["last_run_id"], "run-stub")

        self.store.update(task["task_id"], {"enabled": False})
        self.store.mark_run(task["task_id"], "")
        self.store.update(task["task_id"], {"interval_minutes": 1})
        runner()
        self.assertEqual(len(self.service.requests), 1)


if __name__ == "__main__":
    unittest.main()
