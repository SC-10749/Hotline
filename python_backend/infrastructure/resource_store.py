from __future__ import annotations

import json
import os
import re
import shutil
import sqlite3
import subprocess
from contextlib import contextmanager
from pathlib import Path
from typing import Any
from uuid import uuid4

CHANGE_TYPES = ('added', 'modified', 'deleted', 'tracked')
# shortcut: 快照最多统计 2 万个文件、单文件最大 2MB 计入体积, 何时该升级: 需要精确统计超大仓库时
MAX_SNAPSHOT_FILES = 20000
MAX_SNAPSHOT_FILE_SIZE = 2 * 1024 * 1024
GIT_TIMEOUT_SECONDS = 120
MAX_REMOTE_BRANCHES = 10
GIT_URL_PATTERN = re.compile(r'^(https?://|ssh://|git://|file://|[A-Za-z0-9_.\-]+@[A-Za-z0-9_.\-]+:)')


class ResourceConflictError(ValueError):
    pass


class CheckoutError(ValueError):
    """检出失败；reason 区分失败原因，detail 只放可安全返回的信息。"""

    def __init__(self, message: str, reason: str, detail: dict[str, Any] | None = None):
        super().__init__(message)
        self.reason = reason
        self.detail = detail or {}


def _run_git(args: list[str], cwd: Path | None = None, timeout: int = GIT_TIMEOUT_SECONDS) -> subprocess.CompletedProcess:
    """只调用 git 命令行；参数用数组传递，不拼 shell 字符串。"""
    if shutil.which('git') is None:
        raise CheckoutError('git 命令不可用', 'git_unavailable')
    env = {**os.environ, 'GIT_TERMINAL_PROMPT': '0', 'GIT_ASKPASS': 'echo', 'PYTHONUTF8': '1'}
    try:
        return subprocess.run(['git', *args], cwd=str(cwd) if cwd else None, capture_output=True,
                              text=True, encoding='utf-8', errors='replace', timeout=timeout,
                              env=env, shell=False)
    except subprocess.TimeoutExpired:
        raise CheckoutError('git 操作超时', 'timeout') from None
    except OSError:
        raise CheckoutError('git 命令不可用', 'git_unavailable') from None


def _git_tracked_files(root: Path) -> list[str]:
    result = _run_git(['-C', str(root), 'ls-files', '-z'])
    if result.returncode != 0:
        return []
    return [item for item in result.stdout.split('\x00') if item]


def _git_head_commit(root: Path) -> str:
    result = _run_git(['-C', str(root), 'rev-parse', '--short', 'HEAD'])
    return result.stdout.strip() if result.returncode == 0 else ''


def _load_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return list(value)
    try:
        parsed = json.loads(value or '[]')
    except (TypeError, ValueError):
        return []
    return list(parsed) if isinstance(parsed, list) else []


def _dump_list(value: Any) -> str:
    return json.dumps(list(value or []), ensure_ascii=False)


def _scan_directory(root: Path) -> tuple[int, int, list[str]]:
    """Count files and bytes under a directory, skipping .git."""
    files: list[str] = []
    size_bytes = 0
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [name for name in dirnames if name != '.git']
        for filename in filenames:
            path = Path(dirpath) / filename
            try:
                size = path.stat().st_size
            except OSError:
                size = 0
            if size <= MAX_SNAPSHOT_FILE_SIZE:
                size_bytes += size
            try:
                files.append(path.relative_to(root).as_posix())
            except ValueError:
                continue
            if len(files) >= MAX_SNAPSHOT_FILES:
                return len(files), size_bytes, files
    return len(files), size_bytes, files


class ResourceStore:
    """Durable registry for Harness Agent and workspace definitions."""

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
                CREATE TABLE IF NOT EXISTS harness_agent (
                    agent_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    description TEXT NOT NULL DEFAULT '',
                    version TEXT NOT NULL DEFAULT 'v1',
                    model TEXT NOT NULL DEFAULT 'auto',
                    policy TEXT NOT NULL DEFAULT '{}',
                    status TEXT NOT NULL DEFAULT 'draft',
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS harness_workspace (
                    workspace_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    repository TEXT NOT NULL DEFAULT '',
                    branch TEXT NOT NULL DEFAULT 'main',
                    status TEXT NOT NULL DEFAULT 'ready',
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS harness_agent_version (
                    version_id TEXT PRIMARY KEY,
                    agent_id TEXT NOT NULL,
                    version TEXT NOT NULL DEFAULT 'v1',
                    name TEXT NOT NULL,
                    description TEXT NOT NULL DEFAULT '',
                    model TEXT NOT NULL DEFAULT 'auto',
                    policy TEXT NOT NULL DEFAULT '{}',
                    tools TEXT NOT NULL DEFAULT '[]',
                    skills TEXT NOT NULL DEFAULT '[]',
                    enabled INTEGER NOT NULL DEFAULT 0,
                    revision INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE INDEX IF NOT EXISTS idx_agent_version_agent
                    ON harness_agent_version(agent_id, created_at);
                CREATE TABLE IF NOT EXISTS harness_workspace_snapshot (
                    snapshot_id TEXT PRIMARY KEY,
                    workspace_id TEXT NOT NULL,
                    branch TEXT NOT NULL DEFAULT '',
                    "commit" TEXT NOT NULL DEFAULT '',
                    file_count INTEGER NOT NULL DEFAULT 0,
                    size_bytes INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE INDEX IF NOT EXISTS idx_workspace_snapshot
                    ON harness_workspace_snapshot(workspace_id, created_at);
                CREATE TABLE IF NOT EXISTS harness_workspace_change (
                    change_id TEXT PRIMARY KEY,
                    workspace_id TEXT NOT NULL,
                    snapshot_id TEXT,
                    path TEXT NOT NULL,
                    change_type TEXT NOT NULL DEFAULT 'tracked',
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE INDEX IF NOT EXISTS idx_workspace_change
                    ON harness_workspace_change(workspace_id, snapshot_id);
                CREATE TABLE IF NOT EXISTS harness_workspace_checkout (
                    workspace_id TEXT PRIMARY KEY,
                    repository TEXT NOT NULL DEFAULT '',
                    branch TEXT NOT NULL DEFAULT '',
                    "commit" TEXT NOT NULL DEFAULT '',
                    checkout_dir TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL DEFAULT 'idle',
                    message TEXT NOT NULL DEFAULT '',
                    checked_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                """
            )
            db.execute('BEGIN IMMEDIATE')
            try:
                for table in ('harness_agent', 'harness_workspace'):
                    columns = {row['name'] for row in db.execute(f'PRAGMA table_info({table})')}
                    if 'revision' not in columns:
                        db.execute(f'ALTER TABLE {table} ADD COLUMN revision INTEGER NOT NULL DEFAULT 1')
                columns = {row['name'] for row in db.execute('PRAGMA table_info(harness_agent)')}
                for name, definition in (
                    ('enabled', 'INTEGER NOT NULL DEFAULT 0'),
                    ('tools', "TEXT NOT NULL DEFAULT '[]'"),
                    ('skills', "TEXT NOT NULL DEFAULT '[]'"),
                ):
                    if name not in columns:
                        db.execute(f'ALTER TABLE harness_agent ADD COLUMN {name} {definition}')
                db.commit()
            except Exception:
                db.rollback()
                raise

    @staticmethod
    def _agent_view(row: dict[str, Any]) -> dict[str, Any]:
        row['enabled'] = bool(row.get('enabled'))
        row['tools'] = _load_list(row.get('tools'))
        row['skills'] = _load_list(row.get('skills'))
        return row

    @staticmethod
    def _write_version(db: sqlite3.Connection, row: sqlite3.Row) -> str:
        version_id = f"agentver-{uuid4().hex[:12]}"
        db.execute(
            '''INSERT INTO harness_agent_version
               (version_id,agent_id,version,name,description,model,policy,tools,skills,enabled,revision)
               VALUES(?,?,?,?,?,?,?,?,?,?,?)''',
            (version_id, row['agent_id'], row['version'], row['name'], row['description'], row['model'],
             row['policy'], row['tools'], row['skills'], int(row['enabled'] or 0), row['revision']),
        )
        return version_id

    def list_agents(self) -> list[dict[str, Any]]:
        with self._db() as db:
            rows = db.execute("SELECT * FROM harness_agent ORDER BY updated_at DESC").fetchall()
        return [self._agent_view(dict(row)) for row in rows]

    def create_agent(self, payload: dict[str, Any]) -> dict[str, Any]:
        agent_id = f"agent-{uuid4().hex[:12]}"
        with self._db() as db:
            db.execute('BEGIN IMMEDIATE')
            try:
                db.execute(
                    "INSERT INTO harness_agent(agent_id,name,description,version,model,policy,status,tools,skills)"
                    " VALUES(?,?,?,?,?,?,?,?,?)",
                    (agent_id, payload["name"], payload.get("description", ""), payload.get("version", "v1"),
                     payload.get("model", "auto"), payload.get("policy", "{}"), payload.get("status", "draft"),
                     _dump_list(payload.get("tools")), _dump_list(payload.get("skills"))),
                )
                row = db.execute('SELECT * FROM harness_agent WHERE agent_id=?', (agent_id,)).fetchone()
                self._write_version(db, row)
                db.commit()
            except Exception:
                db.rollback()
                raise
        return self.get_agent(agent_id) or {}

    def get_agent(self, agent_id: str) -> dict[str, Any] | None:
        with self._db() as db:
            row = db.execute("SELECT * FROM harness_agent WHERE agent_id=?", (agent_id,)).fetchone()
        return self._agent_view(dict(row)) if row else None

    def update_agent(self, agent_id: str, payload: dict[str, Any], revision: int) -> dict[str, Any] | None:
        with self._db() as db:
            db.execute('BEGIN IMMEDIATE')
            try:
                current = db.execute('SELECT * FROM harness_agent WHERE agent_id=?', (agent_id,)).fetchone()
                if not current:
                    db.commit()
                    return None
                if current['revision'] != revision:
                    raise ResourceConflictError('Agent 已被修改，请重新打开详情后再保存')
                tools = payload.get('tools')
                tools_json = current['tools'] if tools is None else _dump_list(tools)
                db.execute(
                    '''UPDATE harness_agent SET name=?,description=?,version=?,model=?,policy=?,tools=?,
                       revision=revision+1,updated_at=CURRENT_TIMESTAMP WHERE agent_id=?''',
                    (payload['name'], payload['description'], payload['version'], payload['model'],
                     payload['policy'], tools_json, agent_id),
                )
                row = db.execute('SELECT * FROM harness_agent WHERE agent_id=?', (agent_id,)).fetchone()
                self._write_version(db, row)
                db.commit()
            except Exception:
                db.rollback()
                raise
        return self.get_agent(agent_id)

    def set_agent_status(self, agent_id: str, enabled: bool) -> dict[str, Any] | None:
        """Toggle the agent without touching the editable definition revision."""
        with self._db() as db:
            db.execute('BEGIN IMMEDIATE')
            try:
                current = db.execute('SELECT * FROM harness_agent WHERE agent_id=?', (agent_id,)).fetchone()
                if not current:
                    db.commit()
                    return None
                if bool(current['enabled']) == bool(enabled):
                    db.commit()
                    return self.get_agent(agent_id)
                db.execute('UPDATE harness_agent SET enabled=?,updated_at=CURRENT_TIMESTAMP WHERE agent_id=?',
                           (1 if enabled else 0, agent_id))
                row = db.execute('SELECT * FROM harness_agent WHERE agent_id=?', (agent_id,)).fetchone()
                self._write_version(db, row)
                db.commit()
            except Exception:
                db.rollback()
                raise
        return self.get_agent(agent_id)

    def set_agent_skills(self, agent_id: str, skill_ids: list[str]) -> dict[str, Any] | None:
        """Replace the bound skill ids without touching the editable definition revision."""
        with self._db() as db:
            db.execute('BEGIN IMMEDIATE')
            try:
                current = db.execute('SELECT * FROM harness_agent WHERE agent_id=?', (agent_id,)).fetchone()
                if not current:
                    db.commit()
                    return None
                if _load_list(current['skills']) == list(skill_ids):
                    db.commit()
                    return self.get_agent(agent_id)
                db.execute('UPDATE harness_agent SET skills=?,updated_at=CURRENT_TIMESTAMP WHERE agent_id=?',
                           (_dump_list(skill_ids), agent_id))
                row = db.execute('SELECT * FROM harness_agent WHERE agent_id=?', (agent_id,)).fetchone()
                self._write_version(db, row)
                db.commit()
            except Exception:
                db.rollback()
                raise
        return self.get_agent(agent_id)

    def list_agent_versions(self, agent_id: str) -> list[dict[str, Any]]:
        with self._db() as db:
            rows = db.execute(
                'SELECT * FROM harness_agent_version WHERE agent_id=? ORDER BY created_at DESC, rowid DESC',
                (agent_id,)).fetchall()
        return [dict(row) for row in rows]

    def get_agent_version(self, agent_id: str, version_id: str) -> dict[str, Any] | None:
        with self._db() as db:
            row = db.execute('SELECT * FROM harness_agent_version WHERE agent_id=? AND version_id=?',
                             (agent_id, version_id)).fetchone()
        return dict(row) if row else None

    def list_workspaces(self) -> list[dict[str, Any]]:
        with self._db() as db:
            return [dict(row) for row in db.execute("SELECT * FROM harness_workspace ORDER BY updated_at DESC").fetchall()]

    def create_workspace(self, payload: dict[str, Any]) -> dict[str, Any]:
        workspace_id = f"workspace-{uuid4().hex[:12]}"
        with self._db() as db:
            db.execute(
                "INSERT INTO harness_workspace(workspace_id,name,repository,branch,status) VALUES(?,?,?,?,?)",
                (workspace_id, payload["name"], payload.get("repository", ""), payload.get("branch", "main"), payload.get("status", "ready")),
            )
        return self.get_workspace(workspace_id) or {}

    def get_workspace(self, workspace_id: str) -> dict[str, Any] | None:
        with self._db() as db:
            row = db.execute("SELECT * FROM harness_workspace WHERE workspace_id=?", (workspace_id,)).fetchone()
        return dict(row) if row else None

    def update_workspace(self, workspace_id: str, payload: dict[str, Any], revision: int) -> dict[str, Any] | None:
        with self._db() as db:
            db.execute('BEGIN IMMEDIATE')
            try:
                current = db.execute('SELECT revision FROM harness_workspace WHERE workspace_id=?', (workspace_id,)).fetchone()
                if not current:
                    db.commit()
                    return None
                if current['revision'] != revision:
                    raise ResourceConflictError('工作空间已被修改，请重新打开详情后再保存')
                db.execute(
                    '''UPDATE harness_workspace SET name=?,repository=?,branch=?,revision=revision+1,
                       updated_at=CURRENT_TIMESTAMP WHERE workspace_id=?''',
                    (payload['name'], payload['repository'], payload['branch'], workspace_id),
                )
                row = db.execute('SELECT * FROM harness_workspace WHERE workspace_id=?', (workspace_id,)).fetchone()
                db.commit()
            except Exception:
                db.rollback()
                raise
        return dict(row)

    def resolve_local_repository(self, repository: str) -> Path | None:
        """公开入口：把 repository 当作本地目录解析，解析不到返回 None。"""
        return self._resolve_repository(repository)

    def _resolve_repository(self, repository: str) -> Path | None:
        text = (repository or '').strip()
        if not text:
            return None
        candidate = Path(text).expanduser()
        roots = [candidate] if candidate.is_absolute() else [Path.cwd() / candidate, self.path.parent / candidate]
        for root in roots:
            try:
                resolved = root.resolve()
            except OSError:
                continue
            if resolved.is_dir():
                return resolved
        return None

    def create_workspace_snapshot(self, workspace_id: str, repository: str, branch: str,
                                    root: Path | None = None, commit: str = 'local',
                                    files: list[str] | None = None) -> dict[str, Any]:
        """root 为受管检出目录时用它统计文件；commit 由调用方给出真实哈希。"""
        managed = self._managed_snapshot_source(workspace_id)
        if root is None and managed is not None:
            target = managed
            commit = _git_head_commit(target) or commit
            files = _git_tracked_files(target)
        else:
            target = Path(root) if root else self._resolve_repository(repository)
            if target is None or not target.is_dir():
                raise ValueError('仓库路径不可访问，无法创建快照')
        if files is None:
            file_count, size_bytes, files = _scan_directory(target)
        else:
            files = list(files)
            file_count = len(files)
            size_bytes = sum((target / name).stat().st_size for name in files
                              if (target / name).is_file())
        snapshot_id = f"snapshot-{uuid4().hex[:12]}"
        with self._db() as db:
            db.execute('BEGIN IMMEDIATE')
            try:
                db.execute(
                    '''INSERT INTO harness_workspace_snapshot
                       (snapshot_id,workspace_id,branch,"commit",file_count,size_bytes) VALUES(?,?,?,?,?,?)''',
                    (snapshot_id, workspace_id, branch or '', commit or 'local', file_count, size_bytes),
                )
                db.executemany(
                    '''INSERT INTO harness_workspace_change(change_id,workspace_id,snapshot_id,path,change_type)
                       VALUES(?,?,?,?,?)''',
                    [(f"change-{uuid4().hex[:12]}", workspace_id, snapshot_id, path, 'tracked') for path in files],
                )
                db.commit()
            except Exception:
                db.rollback()
                raise
        return self.get_workspace_snapshot(snapshot_id) or {}

    def _managed_snapshot_source(self, workspace_id: str) -> Path | None:
        """受管检出目录存在时，快照统计该目录而不是 repository 里的本地路径。"""
        row = self.get_workspace_checkout(workspace_id)
        if not row or not row.get('checkout_dir'):
            return None
        path = Path(row['checkout_dir'])
        return path if path.is_dir() else None

    def managed_checkout_dir(self, workspace_id: str) -> Path:
        """受管检出目录：<data_dir>/workspaces/<workspace_id>/repo，只允许落在 data_dir 内。"""
        if not workspace_id or any(char in workspace_id for char in '/\\') or '..' in workspace_id:
            raise CheckoutError('工作空间标识非法', 'invalid_workspace')
        base = (self.path.parent / 'workspaces').resolve()
        target = (base / workspace_id / 'repo').resolve()
        if base != target.parent.parent:
            raise CheckoutError('检出目录超出受管范围', 'invalid_path')
        return target

    def _remote_branches(self, root: Path, limit: int = MAX_REMOTE_BRANCHES) -> list[str]:
        """列出克隆下来的远端分支名；本地已有 refs 时不再访问网络。"""
        result = _run_git(['-C', str(root), 'branch', '-r'], timeout=30)
        branches = []
        if result.returncode == 0:
            for line in result.stdout.splitlines():
                name = line.strip().split('->')[0].strip()
                if name.startswith('origin/') and name != 'origin/HEAD':
                    branches.append(name[len('origin/'):])
        return branches[:limit]

    def checkout_workspace(self, workspace_id: str, repository: str, branch: str) -> dict[str, Any]:
        """把 git 地址浅克隆到受管目录并检出分支，成功后写快照。

        只落盘到 <data_dir>/workspaces/<workspace_id>/repo，不碰用户自己的目录。
        """
        target = self.managed_checkout_dir(workspace_id)
        if target.exists():
            shutil.rmtree(target, ignore_errors=True)
        target.parent.mkdir(parents=True, exist_ok=True)
        clone = _run_git(['clone', '--depth', '1', '--no-single-branch', repository, str(target)])
        if clone.returncode != 0:
            raise CheckoutError('仓库地址不可达或克隆失败', 'unreachable')
        wanted = (branch or '').strip() or 'main'
        checkout = _run_git(['-C', str(target), 'checkout', wanted], timeout=30)
        if checkout.returncode != 0:
            branches = self._remote_branches(target)
            raise CheckoutError('分支不存在', 'branch_not_found', {'branches': branches, 'branch': wanted})
        actual_branch = _run_git(['-C', str(target), 'rev-parse', '--abbrev-ref', 'HEAD'], timeout=30)
        commit = _run_git(['-C', str(target), 'rev-parse', '--short', 'HEAD'], timeout=30)
        files = _git_tracked_files(target)
        snapshot = self.create_workspace_snapshot(
            workspace_id, repository, actual_branch.stdout.strip() or wanted,
            root=target, commit=commit.stdout.strip() or 'local', files=files)
        checkout_row = self.save_workspace_checkout(
            workspace_id, repository, actual_branch.stdout.strip() or wanted,
            commit.stdout.strip() or 'local', str(target), 'checked_out')
        return {'checkout': checkout_row, 'snapshot': snapshot}

    def get_workspace_checkout(self, workspace_id: str) -> dict[str, Any] | None:
        with self._db() as db:
            row = db.execute('SELECT * FROM harness_workspace_checkout WHERE workspace_id=?',
                             (workspace_id,)).fetchone()
        return dict(row) if row else None

    def save_workspace_checkout(self, workspace_id: str, repository: str, branch: str, commit: str,
                                checkout_dir: str, status: str, message: str = '') -> dict[str, Any]:
        with self._db() as db:
            db.execute('BEGIN IMMEDIATE')
            try:
                db.execute(
                    '''INSERT INTO harness_workspace_checkout
                       (workspace_id,repository,branch,"commit",checkout_dir,status,message,checked_at)
                       VALUES(?,?,?,?,?,?,?,CURRENT_TIMESTAMP)
                       ON CONFLICT(workspace_id) DO UPDATE SET
                         repository=excluded.repository, branch=excluded.branch, "commit"=excluded."commit",
                         checkout_dir=excluded.checkout_dir, status=excluded.status,
                         message=excluded.message, checked_at=CURRENT_TIMESTAMP''',
                    (workspace_id, repository or '', branch or '', commit or '', checkout_dir or '',
                     status, message or ''),
                )
                db.commit()
            except Exception:
                db.rollback()
                raise
        return self.get_workspace_checkout(workspace_id) or {}

    def get_workspace_snapshot(self, snapshot_id: str) -> dict[str, Any] | None:
        with self._db() as db:
            row = db.execute('SELECT * FROM harness_workspace_snapshot WHERE snapshot_id=?', (snapshot_id,)).fetchone()
        return dict(row) if row else None

    def list_workspace_snapshots(self, workspace_id: str) -> list[dict[str, Any]]:
        with self._db() as db:
            rows = db.execute(
                'SELECT * FROM harness_workspace_snapshot WHERE workspace_id=? ORDER BY created_at DESC, rowid DESC',
                (workspace_id,)).fetchall()
        return [dict(row) for row in rows]

    def list_workspace_changes(self, workspace_id: str, snapshot_id: str | None = None) -> list[dict[str, Any]]:
        query = 'SELECT * FROM harness_workspace_change WHERE workspace_id=?'
        params: list[Any] = [workspace_id]
        if snapshot_id:
            query += ' AND snapshot_id=?'
            params.append(snapshot_id)
        with self._db() as db:
            rows = db.execute(query + ' ORDER BY created_at, rowid', params).fetchall()
        return [dict(row) for row in rows]

    def create_workspace_change(self, workspace_id: str, path: str, change_type: str,
                                snapshot_id: str | None = None) -> dict[str, Any]:
        if change_type not in CHANGE_TYPES:
            raise ValueError('变更类型不合法')
        change_id = f"change-{uuid4().hex[:12]}"
        with self._db() as db:
            db.execute(
                '''INSERT INTO harness_workspace_change(change_id,workspace_id,snapshot_id,path,change_type)
                   VALUES(?,?,?,?,?)''',
                (change_id, workspace_id, snapshot_id, path, change_type),
            )
            row = db.execute('SELECT * FROM harness_workspace_change WHERE change_id=?', (change_id,)).fetchone()
        return dict(row)
