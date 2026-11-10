from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any
from uuid import uuid4


TERMINAL_RUN_STATUSES = {"completed", "failed", "blocked", "cancelled"}


class EvaluationStore:
    """Durable metadata store for Harness datasets, configs, and evaluation runs."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.path, timeout=30, isolation_level=None)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA busy_timeout = 30000")
        return db

    @contextmanager
    def _db(self):
        db = self._connect()
        try:
            yield db
        finally:
            db.close()

    def _initialize(self) -> None:
        with self._db() as db:
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS evaluation_dataset (
                    dataset_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    dataset_type TEXT NOT NULL,
                    description TEXT NOT NULL DEFAULT '',
                    version INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS evaluation_case (
                    case_id TEXT PRIMARY KEY,
                    dataset_id TEXT NOT NULL,
                    input_text TEXT NOT NULL,
                    expected_output TEXT NOT NULL DEFAULT '',
                    rubric TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(dataset_id) REFERENCES evaluation_dataset(dataset_id) ON DELETE CASCADE
                );
                CREATE INDEX IF NOT EXISTS idx_evaluation_case_dataset
                    ON evaluation_case(dataset_id, created_at);
                CREATE TABLE IF NOT EXISTS evaluation_config (
                    config_id INTEGER PRIMARY KEY CHECK(config_id = 1),
                    payload TEXT NOT NULL,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS evaluation_run (
                    eval_run_id TEXT PRIMARY KEY,
                    dataset_id TEXT NOT NULL,
                    agent TEXT NOT NULL,
                    version TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL,
                    error TEXT,
                    summary TEXT,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    finished_at TEXT,
                    FOREIGN KEY(dataset_id) REFERENCES evaluation_dataset(dataset_id)
                );
                CREATE TABLE IF NOT EXISTS evaluation_snapshot (
                    snapshot_id TEXT PRIMARY KEY,
                    dataset_id TEXT NOT NULL,
                    version INTEGER NOT NULL,
                    payload TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE INDEX IF NOT EXISTS idx_evaluation_snapshot_dataset
                    ON evaluation_snapshot(dataset_id, version);
                CREATE TABLE IF NOT EXISTS evaluation_result (
                    result_id TEXT PRIMARY KEY,
                    eval_run_id TEXT NOT NULL,
                    case_id TEXT NOT NULL,
                    score REAL NOT NULL DEFAULT 0,
                    verdict TEXT NOT NULL,
                    detail TEXT NOT NULL DEFAULT '',
                    actual_output TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE INDEX IF NOT EXISTS idx_evaluation_result_run
                    ON evaluation_result(eval_run_id, created_at);
                """
            )
            db.execute('BEGIN IMMEDIATE')
            try:
                columns = {row['name'] for row in db.execute('PRAGMA table_info(evaluation_dataset)')}
                if 'version' not in columns:
                    db.execute('ALTER TABLE evaluation_dataset ADD COLUMN version INTEGER NOT NULL DEFAULT 1')
                run_columns = {row['name'] for row in db.execute('PRAGMA table_info(evaluation_run)')}
                if 'summary' not in run_columns:
                    db.execute('ALTER TABLE evaluation_run ADD COLUMN summary TEXT')
                db.commit()
            except Exception:
                db.rollback()
                raise

    def list_datasets(self) -> list[dict[str, Any]]:
        with self._db() as db:
            rows = db.execute(
                """
                SELECT d.*, COUNT(c.case_id) AS case_count
                FROM evaluation_dataset d
                LEFT JOIN evaluation_case c ON c.dataset_id = d.dataset_id
                GROUP BY d.dataset_id
                ORDER BY d.updated_at DESC, d.created_at DESC
                """
            ).fetchall()
        return [dict(row) for row in rows]

    def get_dataset(self, dataset_id: str) -> dict[str, Any] | None:
        with self._db() as db:
            dataset = db.execute(
                "SELECT * FROM evaluation_dataset WHERE dataset_id=?", (dataset_id,)
            ).fetchone()
            if not dataset:
                return None
            cases = db.execute(
                "SELECT * FROM evaluation_case WHERE dataset_id=? ORDER BY created_at, case_id",
                (dataset_id,),
            ).fetchall()
        result = dict(dataset)
        result["cases"] = [self._case_dict(row) for row in cases]
        result["case_count"] = len(result["cases"])
        return result

    @staticmethod
    def _case_dict(row: sqlite3.Row) -> dict[str, Any]:
        item = dict(row)
        item["rubric"] = json.loads(item["rubric"] or "{}")
        return item

    def create_dataset(self, name: str, dataset_type: str, description: str = "") -> dict[str, Any]:
        dataset_id = f"dataset-{uuid4().hex[:12]}"
        with self._db() as db:
            db.execute(
                "INSERT INTO evaluation_dataset(dataset_id,name,dataset_type,description) VALUES(?,?,?,?)",
                (dataset_id, name, dataset_type, description),
            )
        return self.get_dataset(dataset_id) or {}

    def delete_dataset(self, dataset_id: str) -> bool:
        with self._db() as db:
            if not db.execute("SELECT 1 FROM evaluation_dataset WHERE dataset_id=?", (dataset_id,)).fetchone():
                return False
            db.execute("DELETE FROM evaluation_case WHERE dataset_id=?", (dataset_id,))
            db.execute("DELETE FROM evaluation_snapshot WHERE dataset_id=?", (dataset_id,))
            db.execute("DELETE FROM evaluation_dataset WHERE dataset_id=?", (dataset_id,))
            return True

    def add_case(self, dataset_id: str, input_text: str, expected_output: str = "",
                 rubric: dict[str, Any] | None = None) -> dict[str, Any]:
        case_id = f"case-{uuid4().hex[:12]}"
        with self._db() as db:
            if not db.execute("SELECT 1 FROM evaluation_dataset WHERE dataset_id=?", (dataset_id,)).fetchone():
                return None
            db.execute(
                "INSERT INTO evaluation_case(case_id,dataset_id,input_text,expected_output,rubric) VALUES(?,?,?,?,?)",
                (case_id, dataset_id, input_text, expected_output, json.dumps(rubric or {}, ensure_ascii=False)),
            )
            db.execute("UPDATE evaluation_dataset SET updated_at=CURRENT_TIMESTAMP WHERE dataset_id=?", (dataset_id,))
            row = db.execute("SELECT * FROM evaluation_case WHERE case_id=?", (case_id,)).fetchone()
        return self._case_dict(row) if row else None

    def add_cases(self, dataset_id: str, cases: list[dict[str, Any]]) -> list[dict[str, Any]] | None:
        """Write a batch of cases in one transaction; returns None when the dataset is missing."""
        created: list[dict[str, Any]] = []
        with self._db() as db:
            if not db.execute("SELECT 1 FROM evaluation_dataset WHERE dataset_id=?", (dataset_id,)).fetchone():
                return None
            for item in cases:
                case_id = f"case-{uuid4().hex[:12]}"
                db.execute(
                    "INSERT INTO evaluation_case(case_id,dataset_id,input_text,expected_output,rubric) VALUES(?,?,?,?,?)",
                    (case_id, dataset_id, item.get("input", ""), item.get("expectedOutput", ""),
                     json.dumps(item.get("rubric") or {}, ensure_ascii=False)),
                )
                row = db.execute("SELECT * FROM evaluation_case WHERE case_id=?", (case_id,)).fetchone()
                created.append(self._case_dict(row))
            db.execute("UPDATE evaluation_dataset SET updated_at=CURRENT_TIMESTAMP WHERE dataset_id=?", (dataset_id,))
        return created

    def delete_case(self, dataset_id: str, case_id: str) -> bool:
        with self._db() as db:
            cursor = db.execute(
                "DELETE FROM evaluation_case WHERE dataset_id=? AND case_id=?", (dataset_id, case_id)
            )
            if cursor.rowcount:
                db.execute("UPDATE evaluation_dataset SET updated_at=CURRENT_TIMESTAMP WHERE dataset_id=?", (dataset_id,))
            return bool(cursor.rowcount)

    def update_case(self, dataset_id: str, case_id: str, input_text: str, expected_output: str, rubric: dict[str, Any]) -> dict[str, Any] | None:
        with self._db() as db:
            db.execute("UPDATE evaluation_case SET input_text=?,expected_output=?,rubric=? WHERE dataset_id=? AND case_id=?", (input_text, expected_output, json.dumps(rubric, ensure_ascii=False), dataset_id, case_id))
            db.execute("UPDATE evaluation_dataset SET updated_at=CURRENT_TIMESTAMP WHERE dataset_id=?", (dataset_id,))
            row = db.execute("SELECT * FROM evaluation_case WHERE case_id=? AND dataset_id=?", (case_id, dataset_id)).fetchone()
        return self._case_dict(row) if row else None

    def create_snapshot(self, dataset_id: str) -> dict[str, Any] | None:
        """Snapshot the current dataset content, then move the dataset to the next version."""
        with self._db() as db:
            dataset = db.execute("SELECT * FROM evaluation_dataset WHERE dataset_id=?", (dataset_id,)).fetchone()
            if not dataset:
                return None
            case_count = db.execute(
                "SELECT COUNT(*) FROM evaluation_case WHERE dataset_id=?", (dataset_id,)
            ).fetchone()[0]
            version = int(dataset["version"] or 1)
            snapshot_id = f"snapshot-{uuid4().hex[:12]}"
            payload = {
                "name": dataset["name"],
                "type": dataset["dataset_type"],
                "description": dataset["description"],
                "case_count": int(case_count),
            }
            db.execute(
                "INSERT INTO evaluation_snapshot(snapshot_id,dataset_id,version,payload) VALUES(?,?,?,?)",
                (snapshot_id, dataset_id, version, json.dumps(payload, ensure_ascii=False)),
            )
            db.execute(
                "UPDATE evaluation_dataset SET version=?, updated_at=CURRENT_TIMESTAMP WHERE dataset_id=?",
                (version + 1, dataset_id),
            )
            row = db.execute("SELECT * FROM evaluation_snapshot WHERE snapshot_id=?", (snapshot_id,)).fetchone()
        return self._snapshot_dict(row)

    def list_snapshots(self, dataset_id: str) -> list[dict[str, Any]]:
        with self._db() as db:
            rows = db.execute(
                "SELECT * FROM evaluation_snapshot WHERE dataset_id=? ORDER BY version DESC, created_at DESC",
                (dataset_id,),
            ).fetchall()
        return [self._snapshot_dict(row) for row in rows]

    @staticmethod
    def _snapshot_dict(row: sqlite3.Row) -> dict[str, Any]:
        item = dict(row)
        item["payload"] = json.loads(item["payload"] or "{}")
        return item

    def get_config(self) -> dict[str, Any]:
        with self._db() as db:
            row = db.execute("SELECT payload,updated_at FROM evaluation_config WHERE config_id=1").fetchone()
        if not row:
            return {"dimensions": [], "gates": [], "updated_at": None}
        return {**json.loads(row["payload"]), "updated_at": row["updated_at"]}

    def save_config(self, payload: dict[str, Any]) -> dict[str, Any]:
        encoded = json.dumps(payload, ensure_ascii=False)
        with self._db() as db:
            db.execute(
                """
                INSERT INTO evaluation_config(config_id,payload) VALUES(1,?)
                ON CONFLICT(config_id) DO UPDATE SET payload=excluded.payload, updated_at=CURRENT_TIMESTAMP
                """,
                (encoded,),
            )
        return self.get_config()

    def create_run(self, dataset_id: str, agent: str, version: str,
                   status: str = "running", error: str | None = None) -> dict[str, Any] | None:
        with self._db() as db:
            if not db.execute("SELECT 1 FROM evaluation_dataset WHERE dataset_id=?", (dataset_id,)).fetchone():
                return None
            eval_run_id = f"eval-{uuid4().hex[:12]}"
            db.execute(
                "INSERT INTO evaluation_run(eval_run_id,dataset_id,agent,version,status,error) VALUES(?,?,?,?,?,?)",
                (eval_run_id, dataset_id, agent, version, status, error),
            )
            row = db.execute("SELECT * FROM evaluation_run WHERE eval_run_id=?", (eval_run_id,)).fetchone()
        return self._run_dict(row) if row else None

    @staticmethod
    def _run_dict(row: sqlite3.Row) -> dict[str, Any]:
        item = dict(row)
        if item.get("summary"):
            try:
                item["summary"] = json.loads(item["summary"])
            except (TypeError, ValueError):
                pass
        return item

    def update_run(self, eval_run_id: str, status: str, error: str | None = None,
                   summary: dict[str, Any] | None = None) -> dict[str, Any] | None:
        with self._db() as db:
            row = db.execute("SELECT * FROM evaluation_run WHERE eval_run_id=?", (eval_run_id,)).fetchone()
            if not row:
                return None
            encoded = json.dumps(summary, ensure_ascii=False) if summary is not None else row["summary"]
            finished = "CURRENT_TIMESTAMP" if status in TERMINAL_RUN_STATUSES else "NULL"
            db.execute(
                f"""UPDATE evaluation_run SET status=?, error=?, summary=?, finished_at=COALESCE({finished}, finished_at)
                    WHERE eval_run_id=?""",
                (status, error, encoded, eval_run_id),
            )
            row = db.execute("SELECT * FROM evaluation_run WHERE eval_run_id=?", (eval_run_id,)).fetchone()
        return self._run_dict(row) if row else None

    def get_run(self, eval_run_id: str) -> dict[str, Any] | None:
        with self._db() as db:
            row = db.execute('SELECT * FROM evaluation_run WHERE eval_run_id=?', (eval_run_id,)).fetchone()
        return self._run_dict(row) if row else None

    def list_runs(self, limit: int = 100) -> list[dict[str, Any]]:
        with self._db() as db:
            rows = db.execute(
                "SELECT * FROM evaluation_run ORDER BY created_at DESC, rowid DESC LIMIT ?", (max(1, min(limit, 200)),)
            ).fetchall()
        return [self._run_dict(row) for row in rows]

    def save_result(self, eval_run_id: str, case_id: str, score: float, verdict: str,
                    detail: str = "", actual_output: str = "") -> dict[str, Any]:
        result_id = f"result-{uuid4().hex[:12]}"
        with self._db() as db:
            db.execute(
                """INSERT INTO evaluation_result(result_id,eval_run_id,case_id,score,verdict,detail,actual_output)
                   VALUES(?,?,?,?,?,?,?)""",
                (result_id, eval_run_id, case_id, float(score), verdict, detail, actual_output),
            )
            row = db.execute("SELECT * FROM evaluation_result WHERE result_id=?", (result_id,)).fetchone()
        return dict(row) if row else {}

    def list_results(self, eval_run_id: str) -> list[dict[str, Any]]:
        with self._db() as db:
            rows = db.execute(
                "SELECT * FROM evaluation_result WHERE eval_run_id=? ORDER BY created_at, rowid",
                (eval_run_id,),
            ).fetchall()
        return [dict(row) for row in rows]
