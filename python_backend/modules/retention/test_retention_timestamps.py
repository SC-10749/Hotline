"""审批保留期：按真实时间判断，不能提前一天清掉当天裁决的记录。

对应规格 S-013。
"""
from __future__ import annotations

import sqlite3
import tempfile
import time
import unittest
from pathlib import Path

from .maintenance import purge_approvals


class ApprovalRetentionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.governance = self.root / 'governance.db'
        db = sqlite3.connect(self.governance)
        db.execute("CREATE TABLE harness_approval (request_id TEXT PRIMARY KEY, status TEXT, created_at TEXT)")
        db.commit()
        db.close()

    def tearDown(self):
        self.temp.cleanup()

    def insert(self, request_id, status, created_at):
        db = sqlite3.connect(self.governance)
        try:
            db.execute("INSERT INTO harness_approval VALUES (?,?,?)", (request_id, status, created_at))
            db.commit()
        finally:
            db.close()

    def test_decided_approval_on_the_cutoff_day_is_kept(self):
        # 截止时刻是 30 天前的同一时刻；当天更晚的记录还没到保留期。
        stamp = time.strftime('%Y-%m-%d 23:59:59', time.gmtime(time.time() - 30 * 86400))
        self.insert('same-day', 'approved', stamp)
        self.assertEqual(purge_approvals(self.governance, 30), 0)

    def test_approval_older_than_the_window_is_purged(self):
        stamp = time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime(time.time() - 31 * 86400))
        self.insert('old', 'approved', stamp)
        self.assertEqual(purge_approvals(self.governance, 30), 1)

    def test_iso_timestamps_still_expire(self):
        self.insert('iso', 'approved', time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(time.time() - 31 * 86400)))
        self.assertEqual(purge_approvals(self.governance, 30), 1)
