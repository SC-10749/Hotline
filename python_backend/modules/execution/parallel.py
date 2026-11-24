"""子任务隔离工作区：并发子任务各自一份独立目录，产出互不覆盖。

隔离分三级，逐级降级，任何一步失败都不让子任务因此报错：
1. worktree：工作区是 git 仓库时，用独立检出目录（与 Orca 的 worktree 思路一致）。
2. copy：不是 git 仓库时复制一份工作区内容。
3. outputs-only：工作区不可用时只保留独立产物目录。
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

GIT_TIMEOUT_SECONDS = 60
MARKER_NAME = '.task-workspace.json'
IGNORED_PATTERNS = shutil.ignore_patterns(
    '.git', 'node_modules', '__pycache__', '.venv', 'dist', 'build', '.idea', '.next'
)


def task_key_for(conversation_id: str, slot: str = '') -> str:
    """子任务的任务键：同一会话下每个 slot 一把锁，互不冲突。"""
    return f"{conversation_id}#{slot}" if slot else conversation_id


def allocate_task_workspace(source_root: Path | None, target_dir: Path) -> dict[str, Any]:
    """给一个子任务分配独立目录。

    返回 {'path', 'mode', 'workspacePath', 'outputsPath', 'message'}。
    同一个 target 重复分配时复用既有目录，不会重新检出。
    """
    target_dir = Path(target_dir)
    marker = target_dir / MARKER_NAME
    existing = _read_marker(marker)
    if existing:
        return existing

    outputs_dir = target_dir / 'outputs'
    try:
        outputs_dir.mkdir(parents=True, exist_ok=True)
    except OSError:
        return _record(marker, target_dir, target_dir, outputs_dir, 'outputs-only',
                       '子任务目录不可用，已降级为共享工作区')

    if source_root is None:
        return _record(marker, target_dir, target_dir, outputs_dir, 'outputs-only',
                       '未指定工作区，子任务只使用独立产物目录')
    source_root = Path(source_root)
    if not source_root.is_dir():
        return _record(marker, target_dir, target_dir, outputs_dir, 'outputs-only',
                       '工作区目录不可用，子任务只使用独立产物目录')

    workspace_dir = target_dir / 'workspace'
    if (source_root / '.git').exists() and _git_worktree(source_root, workspace_dir):
        return _record(marker, target_dir, workspace_dir, outputs_dir, 'worktree',
                       '已为子任务建立独立检出目录')
    try:
        shutil.copytree(source_root, workspace_dir, dirs_exist_ok=True, ignore=IGNORED_PATTERNS)
    except OSError:
        return _record(marker, target_dir, target_dir, outputs_dir, 'outputs-only',
                       '工作区复制失败，子任务只使用独立产物目录')
    return _record(marker, target_dir, workspace_dir, outputs_dir, 'copy',
                   '已为子任务复制独立工作目录')


def _git_worktree(source_root: Path, workspace_dir: Path) -> bool:
    try:
        subprocess.run(
            ['git', 'worktree', 'add', '--detach', str(workspace_dir), 'HEAD'],
            cwd=source_root, check=True, capture_output=True, timeout=GIT_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return workspace_dir.is_dir()


def _read_marker(marker: Path) -> dict[str, Any] | None:
    if not marker.is_file():
        return None
    try:
        record = json.loads(marker.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return None
    if not isinstance(record, dict) or not record.get('path'):
        return None
    return record


def _record(marker: Path, target_dir: Path, workspace_dir: Path, outputs_dir: Path,
            mode: str, message: str) -> dict[str, Any]:
    record = {
        'path': str(target_dir),
        'mode': mode,
        'workspacePath': str(workspace_dir),
        'outputsPath': str(outputs_dir),
        'message': message,
    }
    try:
        marker.write_text(json.dumps(record, ensure_ascii=False), encoding='utf-8')
    except OSError:
        pass
    return record
