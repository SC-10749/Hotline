"""任务锁与停止信号：会话级互斥，Redis 模式下跨实例广播停止。"""
from __future__ import annotations

import os
import threading

from python_backend.config import Settings


class TaskManager:
    def __init__(self, settings: Settings):
        self._events: dict[str, threading.Event] = {}
        self._lock = threading.Lock()
        self._redis = None
        self._instance_id = os.urandom(4).hex()
        if settings.redis_enabled:
            try:
                import redis
                self._redis = redis.Redis(
                    host=settings.redis_host, port=settings.redis_port, db=settings.redis_database,
                    password=settings.redis_password or None, socket_timeout=settings.redis_timeout,
                    decode_responses=True, protocol=2,
                )
                self._redis.ping()
            except Exception as exc:
                raise RuntimeError("Redis task management is enabled but Redis is unavailable") from exc
        self._task_ttl = settings.redis_task_ttl
        self._stop_thread = None
        if self._redis is not None:
            self._stop_thread = threading.Thread(target=self._listen_for_remote_stops, daemon=True)
            self._stop_thread.start()

    def _listen_for_remote_stops(self) -> None:
        try:
            pubsub = self._redis.pubsub(ignore_subscribe_messages=True)
            pubsub.subscribe("agent:stop")
            for message in pubsub.listen():
                conversation_id = message.get("data")
                if not isinstance(conversation_id, str):
                    continue
                with self._lock:
                    event = self._events.get(conversation_id)
                if event:
                    event.set()
        except Exception:
            # Redis connectivity failures are surfaced by task operations; the
            # listener should not take down the HTTP process.
            return

    def _key(self, conversation_id: str) -> str:
        return f"agent:task:{conversation_id}"

    def register(self, conversation_id: str) -> threading.Event:
        with self._lock:
            if self._redis is not None and not self._redis.set(
                self._key(conversation_id), self._instance_id, nx=True, ex=self._task_ttl
            ):
                raise RuntimeError("该会话正在执行中，请稍后再试")
            event = threading.Event()
            self._events[conversation_id] = event
            return event

    def stop(self, conversation_id: str) -> bool:
        with self._lock:
            event = self._events.get(conversation_id)
        if event:
            event.set()
            if self._redis is not None and self._redis.get(self._key(conversation_id)) == self._instance_id:
                self._redis.delete(self._key(conversation_id))
            return True
        if self._redis is not None and self._redis.exists(self._key(conversation_id)):
            self._redis.publish("agent:stop", conversation_id)
            return True
        return False

    def remove(self, conversation_id: str) -> None:
        with self._lock:
            self._events.pop(conversation_id, None)
        if self._redis is not None and self._redis.get(self._key(conversation_id)) == self._instance_id:
            self._redis.delete(self._key(conversation_id))
