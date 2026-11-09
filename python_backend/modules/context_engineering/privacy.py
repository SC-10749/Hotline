"""Sanitize application content before it leaves the local persistence boundary."""
from __future__ import annotations

import re
from pathlib import PurePosixPath
from ipaddress import IPv6Address
from typing import Any

from ..execution.trace import trace_preview


_ENV_BLOCK = re.compile(r'(?is)<(?:private|secret|env)(?:\s[^>]*)?>.*?</(?:private|secret|env)>')
_ENV_FILE = re.compile(r'(?i)(?<![\w])(?:[\w:.-]+[\\/])*\.env(?:[.\w-]*)?')
_DOMAIN = re.compile(r'(?i)(?<![\w@])(?:[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.)+'
                     r'(?:com|net|org|cn|io|ai|dev|app|cloud|internal|local|lan|corp)(?::\d+)?'
                     r'(?:/[^\s<>\"\']*)?\b')
_SECRET = re.compile(r'\b(?:sk-[A-Za-z0-9_-]{16,}|gh[pousr]_[A-Za-z0-9]{20,}|'
                     r'AKIA[A-Z0-9]{16}|eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+)\b')
_ENV_ASSIGNMENT = re.compile(r'(?im)^\s*(?:export\s+)?[A-Z][A-Z0-9_]{2,}\s*=.*$')
_ADDRESS = re.compile(r'(?im)(\b(?:host|server|domain|address|url|dsn|endpoint|port)\b'
                      r'[\"\']?\s*[:=]\s*)(?:\"[^\"\n]*\"|\'[^\'\n]*\'|[^\s,;]+)')
_IPV6 = re.compile(r'(?i)(?<!\w)\[?(?:[0-9a-f]{0,4}:){2,}[0-9a-f:]{0,39}\]?(?::\d+)?')


def private_path(value: str) -> bool:
    """Exclude private files before reading, indexing, uploading or embedding."""
    if not value or any(ord(char) < 32 for char in str(value)):
        return True
    path = PurePosixPath(str(value).replace('\\', '/'))
    for part in path.parts:
        name = part.casefold()
        if (name in {'..', 'private', 'secrets', '.secrets', '.ssh', '.aws', '.azure', '.git',
                     'data', 'node_modules', '__pycache__', '.venv', 'venv', 'dist', 'build'}
                or re.search(r'(^|\.)env($|[._-])', name)
                or '.local.' in name or '.private.' in name
                or name.endswith(('.local', '.private', '.pem', '.key', '.p12', '.pfx'))
                or name.startswith(('id_rsa', 'id_ed25519'))):
            return True
    return path.is_absolute() or ':' in str(path)


def _redact_ipv6(match):
    value = match.group()
    address = value.split(']', 1)[0].lstrip('[') if value.startswith('[') else value
    try:
        IPv6Address(address)
    except ValueError:
        return value
    return '[REDACTED]'


def sanitize_text(value: str) -> str:
    text = _ENV_BLOCK.sub('[PRIVATE CONTENT REMOVED]', str(value))
    text = _ENV_FILE.sub('[PRIVATE FILE REMOVED]', text)
    text = _ENV_ASSIGNMENT.sub('[PRIVATE CONFIG REMOVED]', text)
    safe, _ = trace_preview(text, max(128, len(text) * 12 + 128))
    if not isinstance(safe, str):
        import json
        safe = json.dumps(safe, ensure_ascii=False)
    safe = _ADDRESS.sub(r'\1[REDACTED]', safe)
    return _IPV6.sub(_redact_ipv6, _SECRET.sub('[REDACTED]', _DOMAIN.sub('[REDACTED]', safe)))


def sanitize_value(value: Any) -> Any:
    if isinstance(value, str):
        return sanitize_text(value)
    if isinstance(value, list):
        return [sanitize_value(item) for item in value]
    if isinstance(value, dict):
        safe, _ = trace_preview(value, max(128, len(str(value)) * 12 + 128))
        if isinstance(safe, dict):
            return {key: sanitize_value(item) for key, item in safe.items()}
        return safe
    return value
