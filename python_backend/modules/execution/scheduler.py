"""定时任务调度线程。

与发布观察、保留清理一样是模块级后台线程：应用退出或测试清理前必须调用
stop_schedule_loop()，否则线程会一直持有 SQLite 连接。
"""

from __future__ import annotations

import logging
import threading
from typing import Any, Callable

logger = logging.getLogger(__name__)

INTERVAL_SECONDS = 60.0

_LOCK = threading.Lock()
_THREAD: threading.Thread | None = None
_STOP: threading.Event = threading.Event()
_RUNNERS: list[Callable[[], None]] = []


def run_once() -> list[Any]:
    """执行一轮扫描；单个任务失败不影响其它任务。"""
    results: list[Any] = []
    for runner in list(_RUNNERS):
        try:
            results.append(runner())
        except Exception as exc:  # pragma: no cover - 守护线程不能因单点失败退出
            logger.warning("定时任务扫描失败：%s", exc)
    return results


def _loop(stop_event: threading.Event) -> None:
    while not stop_event.wait(INTERVAL_SECONDS):
        run_once()


def register_runner(runner: Callable[[], None]) -> None:
    """登记扫描回调并确保线程在运行。"""
    global _THREAD, _STOP
    with _LOCK:
        _RUNNERS.append(runner)
        if _THREAD and _THREAD.is_alive():
            return
        stop_event = threading.Event()
        _STOP = stop_event
        thread = threading.Thread(target=_loop, args=(stop_event,), name="harness-schedule-loop", daemon=True)
        _THREAD = thread
        thread.start()


def stop_schedule_loop(timeout: float = 5.0) -> None:
    """停止调度线程（应用退出、测试清理时调用）。"""
    global _THREAD
    with _LOCK:
        thread = _THREAD
        _THREAD = None
        _RUNNERS.clear()
        stop_event = _STOP
        stop_event.set()
    if thread and thread.is_alive():
        thread.join(timeout)
