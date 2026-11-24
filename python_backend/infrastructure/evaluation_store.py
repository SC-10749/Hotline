from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Any
from uuid import uuid4

from .sqlite_base import SqliteStore


TERMINAL_RUN_STATUSES = {"completed", "failed", "blocked", "cancelled"}


class EvaluationStore(SqliteStore):
    """Durable metadata store for Harness datasets, configs, and evaluation runs."""

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
                    turns TEXT NOT NULL DEFAULT '[]',
                    user_profile TEXT NOT NULL DEFAULT '',
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
                if 'epochs' not in run_columns:
                    db.execute('ALTER TABLE evaluation_run ADD COLUMN epochs INTEGER NOT NULL DEFAULT 1')
                if 'provenance' not in run_columns:
                    db.execute("ALTER TABLE evaluation_run ADD COLUMN provenance TEXT NOT NULL DEFAULT ''")
                case_columns = {row['name'] for row in db.execute('PRAGMA table_info(evaluation_case)')}
                if 'turns' not in case_columns:
                    db.execute("ALTER TABLE evaluation_case ADD COLUMN turns TEXT NOT NULL DEFAULT '[]'")
                if 'user_profile' not in case_columns:
                    db.execute("ALTER TABLE evaluation_case ADD COLUMN user_profile TEXT NOT NULL DEFAULT ''")
                result_columns = {row['name'] for row in db.execute('PRAGMA table_info(evaluation_result)')}
                for column, ddl in (('epoch', 'INTEGER NOT NULL DEFAULT 0'),
                                    ('failure_kind', "TEXT NOT NULL DEFAULT ''"),
                                    ('exec_run_id', "TEXT NOT NULL DEFAULT ''"),
                                    ('trace', "TEXT NOT NULL DEFAULT '{}'"),
                                    ('metrics', "TEXT NOT NULL DEFAULT '{}'")):
                    if column not in result_columns:
                        db.execute(f'ALTER TABLE evaluation_result ADD COLUMN {column} {ddl}')
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
        try:
            turns = json.loads(item.get("turns") or "[]")
        except (TypeError, ValueError):
            turns = []
        item["turns"] = turns if isinstance(turns, list) else []
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
                 rubric: dict[str, Any] | None = None, turns: list[str] | None = None,
                 user_profile: str = "") -> dict[str, Any]:
        case_id = f"case-{uuid4().hex[:12]}"
        with self._db() as db:
            if not db.execute("SELECT 1 FROM evaluation_dataset WHERE dataset_id=?", (dataset_id,)).fetchone():
                return None
            db.execute(
                "INSERT INTO evaluation_case(case_id,dataset_id,input_text,expected_output,rubric,turns,user_profile) VALUES(?,?,?,?,?,?,?)",
                (case_id, dataset_id, input_text, expected_output, json.dumps(rubric or {}, ensure_ascii=False),
                 json.dumps(list(turns or []), ensure_ascii=False), user_profile or ""),
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
                    "INSERT INTO evaluation_case(case_id,dataset_id,input_text,expected_output,rubric,turns,user_profile) VALUES(?,?,?,?,?,?,?)",
                    (case_id, dataset_id, item.get("input", ""), item.get("expectedOutput", ""),
                     json.dumps(item.get("rubric") or {}, ensure_ascii=False),
                     json.dumps(list(item.get("turns") or []), ensure_ascii=False),
                     str(item.get("userProfile") or item.get("user_profile") or "")),
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

    def update_case(self, dataset_id: str, case_id: str, input_text: str, expected_output: str,
                     rubric: dict[str, Any], turns: list[str] | None = None,
                     user_profile: str = "") -> dict[str, Any] | None:
        with self._db() as db:
            db.execute(
                "UPDATE evaluation_case SET input_text=?,expected_output=?,rubric=?,turns=?,user_profile=? WHERE dataset_id=? AND case_id=?",
                (input_text, expected_output, json.dumps(rubric, ensure_ascii=False),
                 json.dumps(list(turns or []), ensure_ascii=False), user_profile or "", dataset_id, case_id))
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
            case_rows = db.execute(
                "SELECT case_id,input_text,expected_output,rubric,turns,user_profile FROM evaluation_case WHERE dataset_id=? ORDER BY created_at, case_id",
                (dataset_id,),
            ).fetchall()
            cases = [{"case_id": row["case_id"], "input_text": row["input_text"],
                      "expected_output": row["expected_output"],
                      "rubric": json.loads(row["rubric"] or "{}"),
                      "turns": json.loads(row["turns"] or "[]"),
                      "user_profile": row["user_profile"] or ""} for row in case_rows]
            payload = {
                "name": dataset["name"],
                "type": dataset["dataset_type"],
                "description": dataset["description"],
                "case_count": int(case_count),
                "cases": cases,
                "sha256": hashlib.sha256(
                    json.dumps(cases, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest(),
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
                   status: str = "running", error: str | None = None,
                   epochs: int = 1, provenance: dict[str, Any] | None = None) -> dict[str, Any] | None:
        with self._db() as db:
            if not db.execute("SELECT 1 FROM evaluation_dataset WHERE dataset_id=?", (dataset_id,)).fetchone():
                return None
            eval_run_id = f"eval-{uuid4().hex[:12]}"
            db.execute(
                "INSERT INTO evaluation_run(eval_run_id,dataset_id,agent,version,status,error,epochs,provenance) VALUES(?,?,?,?,?,?,?,?)",
                (eval_run_id, dataset_id, agent, version, status, error, int(epochs or 1),
                 json.dumps(provenance or {}, ensure_ascii=False)),
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
        try:
            item["provenance"] = json.loads(item.get("provenance") or "{}")
        except (TypeError, ValueError):
            item["provenance"] = {}
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
                    detail: str = "", actual_output: str = "", epoch: int = 0,
                    failure_kind: str = "", exec_run_id: str = "",
                    trace: dict[str, Any] | None = None,
                    metrics: dict[str, Any] | None = None) -> dict[str, Any]:
        result_id = f"result-{uuid4().hex[:12]}"
        with self._db() as db:
            db.execute(
                """INSERT INTO evaluation_result(result_id,eval_run_id,case_id,score,verdict,detail,actual_output,epoch,failure_kind,exec_run_id,trace,metrics)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
                (result_id, eval_run_id, case_id, float(score), verdict, detail, actual_output,
                 int(epoch or 0), failure_kind or "", exec_run_id or "",
                 json.dumps(trace or {}, ensure_ascii=False),
                 json.dumps(metrics or {}, ensure_ascii=False)),
            )
            row = db.execute("SELECT * FROM evaluation_result WHERE result_id=?", (result_id,)).fetchone()
        return self._result_dict(row) if row else {}

    def list_results(self, eval_run_id: str) -> list[dict[str, Any]]:
        with self._db() as db:
            rows = db.execute(
                "SELECT * FROM evaluation_result WHERE eval_run_id=? ORDER BY created_at, rowid",
                (eval_run_id,),
            ).fetchall()
        return [self._result_dict(row) for row in rows]

    def find_result(self, eval_run_id: str, case_id: str, epoch: int = 0) -> dict[str, Any] | None:
        with self._db() as db:
            row = db.execute(
                "SELECT * FROM evaluation_result WHERE eval_run_id=? AND case_id=? AND epoch=? ORDER BY rowid LIMIT 1",
                (eval_run_id, case_id, int(epoch or 0)),
            ).fetchone()
        return self._result_dict(row) if row else None

    @staticmethod
    def _result_dict(row: sqlite3.Row) -> dict[str, Any]:
        item = dict(row)
        try:
            item["trace"] = json.loads(item.get("trace") or "{}")
        except (TypeError, ValueError):
            item["trace"] = {}
        try:
            item["metrics"] = json.loads(item.get("metrics") or "{}")
        except (TypeError, ValueError):
            item["metrics"] = {}
        return item
