from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from ...api.routers.governance import create_governance_router
from ...infrastructure.governance_store import GovernanceStore
from ...infrastructure.notification_store import NotificationStore


class ApprovalNotificationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.store = GovernanceStore(root / "governance.db")
        self.notifications = NotificationStore(root / "notifications.db")
        self.settings = {
            "approvalTimeoutSeconds": 120,
            "approvalNotifyEnabled": True,
            "notificationWebhookUrl": "",
        }
        app = FastAPI()
        app.include_router(create_governance_router(
            lambda: [], self.store, None, lambda: self.settings, self.notifications,
        ))
        self.client = TestClient(app)

    def tearDown(self):
        self.temp.cleanup()

    def create_approval(self):
        response = self.client.post("/harness/approvals",
                                    json={"runId": "run-1", "tool": "write", "risk": "high", "detail": "d"})
        return response.json()["approval"]["request_id"]

    def test_decision_records_local_notification(self):
        request_id = self.create_approval()
        decided = self.client.post(f"/harness/approvals/{request_id}/decision",
                                   json={"decision": "approved", "reason": "ok", "operator": "tester"})
        self.assertEqual(decided.status_code, 200)
        items = self.client.get("/harness/approvals/notifications").json()["items"]
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["request_id"], request_id)
        self.assertEqual(items[0]["channel"], "local")
        self.assertEqual(items[0]["payload"]["decision"], "approved")
        self.assertEqual(items[0]["payload"]["operator"], "tester")

    def test_batch_decision_records_notifications(self):
        first = self.create_approval()
        second = self.create_approval()
        response = self.client.post("/harness/approvals/decide-batch", json={
            "requestIds": [first, second], "decision": "rejected", "reason": "no",
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()["items"]), 2)
        items = self.client.get("/harness/approvals/notifications").json()["items"]
        self.assertEqual(len(items), 2)
        self.assertTrue(all(item["payload"]["decision"] == "rejected" for item in items))

    def test_webhook_failure_does_not_break_the_decision(self):
        self.settings["notificationWebhookUrl"] = "http://127.0.0.1:1/hook"
        request_id = self.create_approval()
        decided = self.client.post(f"/harness/approvals/{request_id}/decision",
                                   json={"decision": "approved"})
        self.assertEqual(decided.status_code, 200)
        items = self.client.get("/harness/approvals/notifications").json()["items"]
        self.assertTrue(any(item["channel"] == "webhook" and item["status"] == "failed" for item in items))

    def test_notification_can_be_disabled(self):
        self.settings["approvalNotifyEnabled"] = False
        request_id = self.create_approval()
        self.client.post(f"/harness/approvals/{request_id}/decision", json={"decision": "approved"})
        self.assertEqual(self.client.get("/harness/approvals/notifications").json()["items"], [])

    def test_deciding_twice_returns_conflict(self):
        request_id = self.create_approval()
        self.client.post(f"/harness/approvals/{request_id}/decision", json={"decision": "approved"})
        again = self.client.post(f"/harness/approvals/{request_id}/decision", json={"decision": "approved"})
        self.assertEqual(again.status_code, 409)


if __name__ == '__main__':
    unittest.main()
