"""模型调用适配层：一次性与流式对话，附带 token 用量统计。"""
from __future__ import annotations

import json
import logging
import threading
import time
import urllib.error
import urllib.request
from collections.abc import Iterator

from python_backend.config import Settings
from python_backend.llm import model_config
from python_backend.modules.context_engineering.budget import ContextBudget
from python_backend.modules.context_engineering.privacy import sanitize_value

logger = logging.getLogger(__name__)


class ModelClient:
    def __init__(self, settings: Settings):
        self.settings = settings
        self._usage = threading.local()
        self.last_usage: dict[str, int] | None = None

    @property
    def last_usage(self):
        return getattr(self._usage, 'value', None)

    @last_usage.setter
    def last_usage(self, value):
        self._usage.value = value

    def _record_usage(self, data: dict) -> None:
        usage = data.get("usage") or {}
        if not isinstance(usage, dict) or not usage:
            return
        input_tokens = int(usage.get("prompt_tokens") or usage.get("input_tokens") or 0)
        output_tokens = int(usage.get("completion_tokens") or usage.get("output_tokens") or 0)
        total = int(usage.get("total_tokens") or 0) or (input_tokens + output_tokens)
        if total:
            self.last_usage = {"inputTokens": input_tokens, "outputTokens": output_tokens,
                               "totalTokens": total}

    def chat(self, messages: list[dict[str, str]]) -> str:
        self.last_usage = None
        messages = sanitize_value(messages)
        budget = ContextBudget.from_settings(self.settings)
        budget.check(messages)
        config = model_config(self.settings)
        if not (config['api_key'] and config['base_url'] and config['model']):
            return ""
        payload = json.dumps({"model": config['model'], "messages": messages,
                              "temperature": 0.2, "max_tokens": budget.output_reserve}).encode()
        endpoint = config['base_url'].rstrip("/") + "/chat/completions"
        request = urllib.request.Request(endpoint, data=payload, headers={
            "Content-Type": "application/json", "Authorization": f"Bearer {config['api_key']}"})
        try:
            with urllib.request.urlopen(request, timeout=90) as response:
                data = json.loads(response.read().decode("utf-8"))
            self._record_usage(data)
            return data["choices"][0]["message"]["content"] or ""
        except Exception as exc:
            # 上游失败与「模型返回空」在返回契约上都是空串，但必须留痕：
            # 否则排查时看不出这次回答是失败还是真的没内容。
            logger.warning("模型调用失败：%s", type(exc).__name__)
            return ""

    def stream(self, messages: list[dict[str, str]]) -> Iterator[str]:
        """按上游 SSE 增量返回文本；上游不支持流式时退化为一次性结果。"""
        self.last_usage = None
        buffer: list[str] = []
        size = 0
        flushed_at = time.monotonic()
        for piece in self._stream_pieces(messages):
            buffer.append(piece)
            size += len(piece)
            now = time.monotonic()
            # 50ms 内的碎片合成一帧，避免每个 token 都触发一次前端重排
            if now - flushed_at >= 0.05 or size >= 200:
                yield ''.join(buffer)
                buffer.clear()
                size = 0
                flushed_at = now
        if buffer:
            yield ''.join(buffer)

    def _stream_pieces(self, messages: list[dict[str, str]]) -> Iterator[str]:
        messages = sanitize_value(messages)
        budget = ContextBudget.from_settings(self.settings)
        budget.check(messages)
        config = model_config(self.settings)
        if not (config['api_key'] and config['base_url'] and config['model']):
            return
        endpoint = config['base_url'].rstrip("/") + "/chat/completions"
        headers = {"Content-Type": "application/json",
                   "Authorization": f"Bearer {config['api_key']}"}
        payload = {"model": config['model'], "messages": messages, "temperature": 0.2,
                   "stream": True, "stream_options": {"include_usage": True},
                   "max_tokens": budget.output_reserve}
        try:
            with self._open(endpoint, payload, headers) as response:
                yield from self._read_stream(response)
            return
        except urllib.error.HTTPError as exc:
            if exc.code != 400:
                logger.warning("流式模型调用失败：HTTP %s", exc.code)
                return
        except Exception as exc:
            logger.warning("流式模型调用失败：%s", type(exc).__name__)
            return
        # 部分兼容服务不认 stream_options，去掉后重试一次
        payload.pop("stream_options", None)
        try:
            with self._open(endpoint, payload, headers) as response:
                yield from self._read_stream(response)
        except Exception as exc:
            logger.warning("流式模型重试仍失败：%s", type(exc).__name__)
            return

    def _open(self, endpoint: str, payload: dict, headers: dict):
        request = urllib.request.Request(endpoint, data=json.dumps(payload).encode(), headers=headers)
        return urllib.request.urlopen(request, timeout=90)

    def _read_stream(self, response) -> Iterator[str]:
        content_type = (response.headers.get("Content-Type") or "").lower()
        if "text/event-stream" not in content_type:
            # 上游忽略了 stream 参数，仍按一次性 JSON 处理
            data = json.loads(response.read().decode("utf-8"))
            self._record_usage(data)
            content = ((data.get("choices") or [{}])[0].get("message") or {}).get("content") or ""
            if content:
                yield content
            return
        for raw in response:
            line = raw.decode("utf-8", errors="ignore").strip()
            if not line.startswith("data:"):
                continue
            data = line[len("data:"):].strip()
            if not data:
                continue
            if data == "[DONE]":
                return
            try:
                chunk = json.loads(data)
            except json.JSONDecodeError:
                continue
            self._record_usage(chunk)
            piece = ((chunk.get("choices") or [{}])[0].get("delta") or {}).get("content") or ""
            if piece:
                yield piece
