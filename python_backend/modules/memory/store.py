"""Local evidence, task checkpoints and a durable OpenViking delivery queue."""
from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4

from .openviking import memory_uri_belongs


class MemoryConflict(ValueError):
    pass


class MemoryStore:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.db() as db:
            db.execute('PRAGMA journal_mode=WAL')
            db.executescript('''
                CREATE TABLE IF NOT EXISTS memory_scope (
                    scope_id TEXT PRIMARY KEY, generation INTEGER NOT NULL DEFAULT 1);
                CREATE TABLE IF NOT EXISTS memory_conversation (
                    conversation_id TEXT PRIMARY KEY, scope_id TEXT NOT NULL,
                    workspace_id TEXT NOT NULL, state_json TEXT NOT NULL DEFAULT '{}',
                    revision INTEGER NOT NULL DEFAULT 0, summary TEXT NOT NULL DEFAULT '',
                    summary_through TEXT NOT NULL DEFAULT '');
                CREATE TABLE IF NOT EXISTS memory_event (
                    conversation_id TEXT NOT NULL, source_id TEXT NOT NULL,
                    question TEXT NOT NULL, answer TEXT NOT NULL DEFAULT '',
                    created_at REAL NOT NULL, completed INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY(conversation_id, source_id));
                CREATE INDEX IF NOT EXISTS idx_memory_event_conversation
                    ON memory_event(conversation_id, created_at);
                CREATE VIRTUAL TABLE IF NOT EXISTS memory_event_fts USING fts5(
                    content, conversation_id UNINDEXED, source_id UNINDEXED, tokenize='trigram');
                CREATE TABLE IF NOT EXISTS memory_delivery (
                    job_id TEXT PRIMARY KEY, conversation_id TEXT NOT NULL, scope_id TEXT NOT NULL,
                    generation INTEGER NOT NULL, source_id TEXT NOT NULL, payload TEXT NOT NULL,
                    stage TEXT NOT NULL DEFAULT 'pending', attempts INTEGER NOT NULL DEFAULT 0,
                    available_at REAL NOT NULL DEFAULT 0, lease_until REAL NOT NULL DEFAULT 0,
                    lease_token TEXT NOT NULL DEFAULT '', task_id TEXT NOT NULL DEFAULT '',
                    error_code TEXT NOT NULL DEFAULT '', created_at REAL NOT NULL);
                CREATE INDEX IF NOT EXISTS idx_memory_delivery_ready
                    ON memory_delivery(stage, available_at, lease_until);
                CREATE INDEX IF NOT EXISTS idx_memory_delivery_scope
                    ON memory_delivery(scope_id, generation, stage, created_at);
                CREATE TABLE IF NOT EXISTS memory_blocked_uri (
                    scope_id TEXT NOT NULL, generation INTEGER NOT NULL, uri TEXT NOT NULL,
                    PRIMARY KEY(scope_id, generation, uri));
                CREATE TABLE IF NOT EXISTS memory_checkpoint (
                    conversation_id TEXT NOT NULL, through_id TEXT NOT NULL,
                    start_id TEXT NOT NULL, summary TEXT NOT NULL, created_at REAL NOT NULL,
                    PRIMARY KEY(conversation_id, through_id));
                CREATE VIRTUAL TABLE IF NOT EXISTS memory_checkpoint_fts USING fts5(
                    content, conversation_id UNINDEXED, through_id UNINDEXED, tokenize='trigram');
            ''')

    @contextmanager
    def db(self):
        db = sqlite3.connect(self.path, timeout=30)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def bind(self, conversation_id: str, workspace_id: str = '') -> dict:
        if not conversation_id or len(conversation_id) > 255 or len(workspace_id) > 255:
            raise ValueError('会话或工作区标识无效')
        scope_id = hashlib.sha256((('workspace:' + workspace_id) if workspace_id
                                   else ('conversation:' + conversation_id)).encode()).hexdigest()[:32]
        with self.db() as db:
            db.execute('INSERT OR IGNORE INTO memory_scope(scope_id) VALUES(?)', (scope_id,))
            db.execute('INSERT OR IGNORE INTO memory_conversation(conversation_id,scope_id,workspace_id) '
                       'VALUES(?,?,?)', (conversation_id, scope_id, workspace_id))
            row = db.execute('SELECT * FROM memory_conversation WHERE conversation_id=?',
                             (conversation_id,)).fetchone()
            if row['scope_id'] != scope_id:
                raise MemoryConflict('会话已绑定其他范围，请使用新的会话')
        return self.conversation(conversation_id)

    def conversation(self, conversation_id: str) -> dict | None:
        with self.db() as db:
            row = db.execute('''SELECT c.*,s.generation FROM memory_conversation c
                JOIN memory_scope s ON c.scope_id=s.scope_id WHERE conversation_id=?''',
                             (conversation_id,)).fetchone()
        if row is None:
            return None
        result = dict(row)
        result['state'] = json.loads(result.pop('state_json'))
        result['peer_id'] = f"hotline-{result['scope_id']}-{result['generation']}"
        return result

    def put_state(self, conversation_id: str, state: dict, revision: int) -> dict:
        with self.db() as db:
            changed = db.execute('''UPDATE memory_conversation SET state_json=?,revision=revision+1
                WHERE conversation_id=? AND revision=?''',
                                 (json.dumps(state, ensure_ascii=False), conversation_id, revision)).rowcount
            if not changed:
                raise MemoryConflict('任务状态已更新，请重新读取后重试')
        return self.conversation(conversation_id)

    def save_summary(self, conversation_id: str, through: str, summary: str, revision: int,
                     *, segment: str = '', start: str = '') -> bool:
        with self.db() as db:
            changed = bool(db.execute('''UPDATE memory_conversation SET summary=?,summary_through=?,
                revision=revision+1 WHERE conversation_id=? AND revision=?''',
                                   (summary, through, conversation_id, revision)).rowcount)
            if changed and segment:
                db.execute('INSERT OR REPLACE INTO memory_checkpoint VALUES(?,?,?,?,?)',
                           (conversation_id, through, start, segment, time.time()))
                db.execute('DELETE FROM memory_checkpoint_fts WHERE conversation_id=? AND through_id=?',
                           (conversation_id, through))
                db.execute('INSERT INTO memory_checkpoint_fts VALUES(?,?,?)', (segment, conversation_id, through))
            return changed

    def search_checkpoints(self, conversation_id: str, query: str, limit: int = 3) -> list[dict]:
        terms = re.findall(r'[\w\u4e00-\u9fff]{3,}', query)[:12]
        if not terms:
            return []
        match = ' OR '.join('"' + term[:80].replace('"', '""') + '"' for term in terms)
        with self.db() as db:
            rows = db.execute('''SELECT c.* FROM memory_checkpoint_fts f JOIN memory_checkpoint c
                ON c.conversation_id=f.conversation_id AND c.through_id=f.through_id
                WHERE memory_checkpoint_fts MATCH ? AND c.conversation_id=? ORDER BY rank LIMIT ?''',
                              (match, conversation_id, limit)).fetchall()
        return [dict(row) for row in rows]

    def record(self, conversation_id: str, source_id: str, question: str, answer: str = '',
               *, completed: bool = False, payload: dict | None = None) -> None:
        """Completion and its delivery job commit in the same transaction."""
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            scope = db.execute('''SELECT c.scope_id,s.generation FROM memory_conversation c
                JOIN memory_scope s ON s.scope_id=c.scope_id WHERE conversation_id=?''',
                               (conversation_id,)).fetchone()
            if scope is None:
                raise MemoryConflict('会话范围不存在')
            old = db.execute('SELECT completed FROM memory_event WHERE conversation_id=? AND source_id=?',
                             (conversation_id, source_id)).fetchone()
            if old and old['completed'] and not completed:
                return
            db.execute('''INSERT INTO memory_event VALUES(?,?,?,?,?,?)
                ON CONFLICT(conversation_id,source_id) DO UPDATE SET
                question=excluded.question,answer=excluded.answer,completed=excluded.completed''',
                       (conversation_id, source_id, question, answer, time.time(), int(completed)))
            db.execute('DELETE FROM memory_event_fts WHERE conversation_id=? AND source_id=?',
                       (conversation_id, source_id))
            db.execute('INSERT INTO memory_event_fts VALUES(?,?,?)',
                       (question + '\n' + answer, conversation_id, source_id))
            if completed and payload:
                identity = f"{scope['scope_id']}:{scope['generation']}:{conversation_id}:{source_id}"
                job_id = 'mem-' + hashlib.sha256(identity.encode()).hexdigest()[:40]
                db.execute('''INSERT OR IGNORE INTO memory_delivery
                    (job_id,conversation_id,scope_id,generation,source_id,payload,created_at)
                    VALUES(?,?,?,?,?,?,?)''', (job_id, conversation_id, scope['scope_id'],
                    scope['generation'], source_id, json.dumps(payload, ensure_ascii=False), time.time()))

    def events(self, conversation_id: str, limit: int = 100) -> list[dict]:
        with self.db() as db:
            rows = db.execute('''SELECT * FROM memory_event WHERE conversation_id=?
                ORDER BY created_at DESC,rowid DESC LIMIT ?''', (conversation_id, limit)).fetchall()
        return [dict(row) for row in reversed(rows)]

    def mark_completed(self, conversation_id: str, source_id: str):
        with self.db() as db:
            db.execute('''UPDATE memory_conversation SET
                state_json=json_set(state_json,'$.lastCompletedSourceId',?),revision=revision+1
                WHERE conversation_id=?''', (source_id, conversation_id))

    def iter_events(self, conversation_id: str):
        with self.db() as db:
            upper = db.execute('SELECT COALESCE(MAX(rowid),0) FROM memory_event WHERE conversation_id=?',
                               (conversation_id,)).fetchone()[0]
        cursor = 0
        while cursor < upper:
            with self.db() as db:
                rows = db.execute('''SELECT rowid AS cursor,* FROM memory_event
                    WHERE conversation_id=? AND rowid>? AND rowid<=? ORDER BY rowid LIMIT 500''',
                                  (conversation_id, cursor, upper)).fetchall()
            if not rows:
                return
            cursor = rows[-1]['cursor']
            for row in rows:
                yield dict(row)

    def source(self, conversation_id: str, source_id: str) -> dict | None:
        with self.db() as db:
            if source_id.startswith('checkpoint:'):
                row = db.execute('SELECT * FROM memory_checkpoint WHERE conversation_id=? AND through_id=?',
                                 (conversation_id, source_id[len('checkpoint:'):])).fetchone()
                return {'question': '阶段摘要', 'answer': row['summary'], 'source_id': source_id} if row else None
            if source_id.startswith('delivery:'):
                row = db.execute('''SELECT e.* FROM memory_delivery d
                    JOIN memory_event e ON e.conversation_id=d.conversation_id AND e.source_id=d.source_id
                    JOIN memory_conversation c ON c.scope_id=d.scope_id AND c.conversation_id=?
                    JOIN memory_scope s ON s.scope_id=d.scope_id AND s.generation=d.generation
                    WHERE d.job_id=?''', (conversation_id, source_id.removeprefix('delivery:'))).fetchone()
            else:
                row = db.execute('SELECT * FROM memory_event WHERE conversation_id=? AND source_id=?',
                                 (conversation_id, source_id)).fetchone()
        return dict(row) if row else None

    def pending_sources(self, conversation_id: str, limit: int = 4) -> list[dict]:
        with self.db() as db:
            rows = db.execute('''SELECT e.*,d.job_id FROM memory_delivery d
                JOIN memory_event e ON e.conversation_id=d.conversation_id AND e.source_id=d.source_id
                JOIN memory_conversation c ON c.scope_id=d.scope_id AND c.conversation_id=?
                JOIN memory_scope s ON s.scope_id=d.scope_id AND s.generation=d.generation
                WHERE d.stage IN ('pending','committing','extracting')
                ORDER BY d.created_at DESC LIMIT ?''', (conversation_id, limit)).fetchall()
        return [dict(row) for row in rows]

    def search_history(self, conversation_id: str, query: str, limit: int = 6) -> list[dict]:
        words = re.findall(r'[\w\u4e00-\u9fff]{2,}', query)[:12]
        if not words:
            return []
        terms = [word[:80] for word in words if len(word) >= 3]
        with self.db() as db:
            if terms:
                match = ' OR '.join('"' + word.replace('"', '""') + '"' for word in terms)
                rows = db.execute('''SELECT e.* FROM memory_event_fts f
                    JOIN memory_event e ON e.conversation_id=f.conversation_id AND e.source_id=f.source_id
                    WHERE memory_event_fts MATCH ? AND e.conversation_id=? AND e.completed=1
                    ORDER BY rank LIMIT ?''', (match, conversation_id, limit)).fetchall()
            else:
                predicates = ' OR '.join('(question LIKE ? OR answer LIKE ?)' for _ in words)
                params = [conversation_id]
                for word in words:
                    escaped = word.replace('%', '\\%').replace('_', '\\_')
                    params.extend(['%' + escaped + '%'] * 2)
                rows = db.execute(f'''SELECT * FROM memory_event WHERE conversation_id=? AND completed=1
                    AND ({predicates}) ORDER BY created_at DESC LIMIT ?''', (*params, limit)).fetchall()
        return [dict(row) for row in rows]

    def claim(self, lease_seconds: int = 120) -> dict | None:
        now = time.time()
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('''SELECT * FROM memory_delivery WHERE stage NOT IN ('done','cancelled')
                AND available_at<=? AND lease_until<=? ORDER BY created_at LIMIT 1''', (now, now)).fetchone()
            if row is None:
                return None
            token = uuid4().hex
            db.execute('UPDATE memory_delivery SET lease_until=?,lease_token=? WHERE job_id=?',
                       (now + lease_seconds, token, row['job_id']))
        result = dict(row)
        result['lease_token'] = token
        result['payload'] = json.loads(result['payload'])
        return result

    def delivery_update(self, job: dict, stage: str, *, task_id: str = '', error: str = '',
                        retry_seconds: float = 0, release: bool = False) -> None:
        with self.db() as db:
            changed = db.execute('''UPDATE memory_delivery SET stage=?,task_id=?,error_code=?,
                attempts=attempts+?,available_at=?,lease_until=CASE WHEN ? THEN 0 ELSE lease_until END
                WHERE job_id=? AND lease_token=?''',
                (stage, task_id, error, int(bool(error)), time.time() + retry_seconds,
                 int(release), job['job_id'], job['lease_token'])).rowcount
            if not changed:
                raise MemoryConflict('记忆任务租约已失效')

    def deliveries(self, conversation_id: str) -> list[dict]:
        with self.db() as db:
            rows = db.execute('''SELECT job_id,stage,attempts,task_id,error_code FROM memory_delivery
                WHERE conversation_id=? ORDER BY created_at DESC LIMIT 100''', (conversation_id,)).fetchall()
        return [dict(row) for row in rows]

    def blocked_uris(self, scope_id: str, generation: int) -> set[str]:
        with self.db() as db:
            rows = db.execute('SELECT uri FROM memory_blocked_uri WHERE scope_id=? AND generation=?',
                              (scope_id, generation)).fetchall()
        return {row['uri'] for row in rows}

    def queue_delete(self, conversation_id: str, scope: dict, uri: str, *, sessions=False) -> None:
        with self.db() as db:
            previous = db.execute('''SELECT job_id,task_id FROM memory_delivery
                WHERE scope_id=? AND generation=? AND job_id LIKE 'mem-%' ''',
                                  (scope['scope_id'], scope['generation'])).fetchall() if sessions else []
            payload = json.dumps({'operation': 'delete', 'uri': uri,
                                  'sessions': [row['job_id'] for row in previous],
                                  'tasks': [row['task_id'] for row in previous if row['task_id']]})
            db.execute('''INSERT INTO memory_delivery
                (job_id,conversation_id,scope_id,generation,source_id,payload,created_at)
                VALUES(?,?,?,?,?,?,?)''', ('delete-' + uuid4().hex, conversation_id, scope['scope_id'],
                                          scope['generation'], '', payload, time.time()))

    def scope_conversations(self, scope_id: str) -> list[str]:
        with self.db() as db:
            return [row[0] for row in db.execute('SELECT conversation_id FROM memory_conversation WHERE scope_id=?',
                                                (scope_id,)).fetchall()]

    def block_uri(self, conversation_id: str, uri: str) -> None:
        scope = self.conversation(conversation_id)
        if scope is None or not memory_uri_belongs(scope['peer_id'], uri):
            raise ValueError('记忆路径不属于当前范围')
        with self.db() as db:
            db.execute('INSERT OR IGNORE INTO memory_blocked_uri VALUES(?,?,?)',
                       (scope['scope_id'], scope['generation'], uri))

    def forget(self, conversation_id: str) -> dict | None:
        """Rotate the whole shared namespace before deleting any local evidence."""
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            scope = db.execute('''SELECT c.scope_id,s.generation FROM memory_conversation c
                JOIN memory_scope s ON s.scope_id=c.scope_id WHERE conversation_id=?''',
                               (conversation_id,)).fetchone()
            if scope is None:
                return None
            db.execute('UPDATE memory_scope SET generation=generation+1 WHERE scope_id=?', (scope['scope_id'],))
            db.execute("UPDATE memory_delivery SET stage='cancelled',lease_token='',lease_until=0 "
                       "WHERE scope_id=? AND stage NOT IN ('done','cancelled') AND job_id LIKE 'mem-%'",
                       (scope['scope_id'],))
            db.execute('DELETE FROM memory_event_fts WHERE conversation_id=?', (conversation_id,))
            db.execute('DELETE FROM memory_event WHERE conversation_id=?', (conversation_id,))
            db.execute('DELETE FROM memory_checkpoint_fts WHERE conversation_id=?', (conversation_id,))
            db.execute('DELETE FROM memory_checkpoint WHERE conversation_id=?', (conversation_id,))
            db.execute("UPDATE memory_delivery SET payload='{}' WHERE conversation_id=? AND job_id LIKE 'mem-%'",
                       (conversation_id,))
            db.execute('DELETE FROM memory_conversation WHERE conversation_id=?', (conversation_id,))
        return {'scope_id': scope['scope_id'], 'generation': scope['generation'],
                'peer_id': f"hotline-{scope['scope_id']}-{scope['generation']}"}
