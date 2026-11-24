"""Bounded local previews; never change the values passed to a tool or model."""
from __future__ import annotations

import json
import re
from typing import Any


_PRIVATE_KEY = re.compile(r"password|passwd|secret|token|apikey|authorization|credential|privatekey|connectionstring|baseurl|endpoint|hostname|serviceaddress|dsn", re.I)
_PRIVATE_TEXT = re.compile(
    r"(?im)(\b(?:api[_-]?key|password|passwd|secret|access[_-]?token|refresh[_-]?token|authorization)\b[\"']?\s*[:=]\s*)"
    r"(?:\"[^\"\n]*\"|'[^'\n]*'|[^\s,;]+)"
)
_URL = re.compile(r"\b(?:https?|wss?|postgres(?:ql)?|mysql|redis|mongodb(?:\+srv)?|amqp)://[^\s\"'<>]+", re.I)
_IP = re.compile(r"(?<![\w.])(?:\d{1,3}\.){3}\d{1,3}(?::\d+)?(?![\w.])")


def trace_preview(value, limit: int) -> tuple[object, bool]:
    def clean(item, depth=0):
        if depth > 20:
            return '[DEPTH LIMIT]'
        if isinstance(item, dict):
            return {str(key): '[REDACTED]' if _PRIVATE_KEY.search(re.sub(r'[_\s-]', '', str(key)))
                    else clean(child, depth + 1) for key, child in item.items()}
        if isinstance(item, (list, tuple)):
            return [clean(child, depth + 1) for child in item]
        if isinstance(item, str):
            text = re.sub(r'-----BEGIN [^-]*PRIVATE KEY-----.*?-----END [^-]*PRIVATE KEY-----',
                          '[REDACTED]', item, flags=re.S)
            text = re.sub(r'(?i)\bBearer\s+[^\s\"\',;]+', 'Bearer [REDACTED]', text)
            text = _PRIVATE_TEXT.sub(r'\1[REDACTED]', text)
            return _IP.sub('[REDACTED]', _URL.sub('[REDACTED]', text))
        if item is None or isinstance(item, (bool, int, float)):
            return item
        return f'[{type(item).__name__}]'

    if isinstance(value, str):
        try:
            value = json.loads(value)
        except (ValueError, RecursionError):
            pass
    safe = clean(value)
    encoded = json.dumps(safe, ensure_ascii=False)
    if len(encoded) > limit:
        return encoded[:limit] + '…', True
    return safe, False
