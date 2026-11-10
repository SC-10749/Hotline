from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from .maintenance import purge_approvals, purge_artifacts, purge_execution_history, run_retention


OLD = '2000-01-01T00:00:00Z'
NEW = '2999-01-01T00:00:00Z'


class RetentionTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.execution = self.root / 'execution.db'
        self.governance = self.root / 'governance.db'
        self.artifacts = self.root / 'artifacts.db'
        db = sqlite3.connect(self.execution)
        db.executescript('''
            CREATE TABLE execution_run (run_id TEXT PRIMARY KEY, status TEXT, created_at TEXT);
            CREATE TABLE execution_event (event_id INTEGER PRIMARY KEY, run_id TEXT, created_at TEXT);
        ''')
        db.execute("INSERT INTO execution_run VALUES ('old','completed',?)", (OLD,))
        db.execute("INSERT INTO execution_run VALUES ('new','completed',?)", (NEW,))
        db.execute("INSERT INTO execution_event VALUES (1,'old',?)", (OLD,))
        db.execute("INSERT INTO execution_event VALUES (2,'new',?)", (NEW,))
        db.commit()
        db.close()
        db = sqlite3.connect(self.governance)
        db.execute("CREATE TABLE harness_approval (request_id TEXT PRIMARY KEY, status TEXT, created_at TEXT)")
        db.execute("INSERT INTO harness_approval VALUES ('a','approved',?)", (OLD,))
        db.execute("INSERT INTO harness_approval VALUES ('b','pending',?)", (OLD,))
        db.commit()
        db.close()
        db = sqlite3.connect(self.artifacts)
        db.execute("CREATE TABLE run_artifact (artifact_id TEXT PRIMARY KEY, created_at TEXT)")
        db.execute("INSERT INTO run_artifact VALUES ('x',?)", (OLD,))
        db.execute("INSERT INTO run_artifact VALUES ('y',?)", (NEW,))
        db.commit()
        db.close()

    def tearDown(self):
        self.tmp.cleanup()

    def test_execution_history_keeps_recent_rows(self):
        result = purge_execution_history(self.execution, 30)
        self.assertEqual(result['runs'], 1)
        self.assertEqual(result['events'], 1)

    def test_pending_approvals_are_never_purged(self):
        self.assertEqual(purge_approvals(self.governance, 30), 1)

    def test_artifact_registrations_expire(self):
        self.assertEqual(purge_artifacts(self.artifacts, 30), 1)

    def test_run_retention_applies_all_windows(self):
        result = run_retention(
            {'execution': self.execution, 'governance': self.governance, 'artifacts': self.artifacts},
            {'auditRetentionDays': 30, 'artifactRetentionDays': 30},
        )
        self.assertEqual(result['approvals'], 1)
        self.assertEqual(result['artifacts'], 1)


if __name__ == '__main__':
    unittest.main()
