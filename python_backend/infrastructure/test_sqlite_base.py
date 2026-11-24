from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from .sqlite_base import SqliteStore


class _Store(SqliteStore):
    """测试用的最小 store：只借基类的连接、事务与补列能力。"""

    def _initialize(self) -> None:
        with self._db() as db:
            db.execute("CREATE TABLE IF NOT EXISTS item (id INTEGER PRIMARY KEY, name TEXT NOT NULL)")


class SqliteStoreTests(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.TemporaryDirectory()
        self.path = Path(self.root.name) / "state.db"
        self.store = _Store(self.path)

    def tearDown(self):
        self.root.cleanup()

    def test_transaction_commits_on_success(self):
        with self.store._transaction() as db:
            db.execute("INSERT INTO item(name) VALUES('a')")
        with self.store._db() as db:
            rows = db.execute("SELECT name FROM item").fetchall()
        self.assertEqual([row["name"] for row in rows], ["a"])

    def test_transaction_rolls_back_and_reraises(self):
        class Boom(RuntimeError):
            pass

        with self.assertRaises(Boom):
            with self.store._transaction() as db:
                db.execute("INSERT INTO item(name) VALUES('b')")
                raise Boom()
        with self.store._db() as db:
            rows = db.execute("SELECT name FROM item").fetchall()
        self.assertEqual(rows, [])

    def test_ensure_columns_adds_missing_columns_only(self):
        with self.store._db() as db:
            self.store.ensure_columns(db, "item", {"weight": "INTEGER NOT NULL DEFAULT 0"})
            columns = {row["name"] for row in db.execute("PRAGMA table_info(item)")}
            self.assertIn("weight", columns)
            # 幂等：再调一次不应报错，也不应重复添加。
            self.store.ensure_columns(db, "item", {"weight": "INTEGER NOT NULL DEFAULT 0"})
            again = {row["name"] for row in db.execute("PRAGMA table_info(item)")}
        self.assertEqual(columns, again)

    def test_ensure_columns_keeps_existing_values(self):
        with self.store._db() as db:
            db.execute("INSERT INTO item(name) VALUES('c')")
        with self.store._db() as db:
            self.store.ensure_columns(db, "item", {"weight": "INTEGER NOT NULL DEFAULT 7"})
            row = db.execute("SELECT name, weight FROM item").fetchone()
        self.assertEqual(row["name"], "c")
        self.assertEqual(row["weight"], 7)

    def test_connect_applies_busy_timeout(self):
        with self.store._db() as db:
            timeout = db.execute("PRAGMA busy_timeout").fetchone()[0]
        self.assertEqual(timeout, 30000)


class SqliteStoreTimeoutTests(unittest.TestCase):
    def test_timeout_override_is_honoured(self):
        class ShortTimeoutStore(_Store):
            timeout = 10

        with tempfile.TemporaryDirectory() as root:
            store = ShortTimeoutStore(Path(root) / "state.db")
            with store._db() as db:
                self.assertIsInstance(db, sqlite3.Connection)
                self.assertEqual(db.execute("PRAGMA busy_timeout").fetchone()[0], 30000)


if __name__ == "__main__":
    unittest.main()
