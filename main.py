"""FastAPI entrypoint for Dodo Agent.

Run:
  uv run fastapi dev
  uv run fastapi dev main.py --port 8888
  python -m uvicorn main:app --reload --port 8888
"""

from __future__ import annotations

import os
from pathlib import Path

# The env file carries credentials plus the deployment's own settings. Most of those
# settings are useful locally (pgvector, chunking, MinerU), but the ones below describe
# the production box: honouring them would silently move a dev server onto remote
# MySQL / Redis / MinIO, so they are read only when exported by hand.
REMOTE_ONLY_KEYS = ("DODO_STORAGE_BACKEND", "DODO_FILE_STORAGE_BACKEND", "DODO_REDIS_ENABLED")
REMOTE_ONLY_PREFIXES = ("DODO_MYSQL_", "DODO_REDIS_", "DODO_MINIO_")
workspace_env = Path(__file__).resolve().parent / ".env"
env_file = Path(os.environ.get("DODO_ENV_FILE", str(workspace_env))).expanduser()
remote_profile = os.environ.get("DODO_ENV_PROFILE", "local").lower() == "remote"
if env_file.exists():
    file_values = {}
    for line in env_file.read_text("utf-8").splitlines():
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip()
        if not key or key.startswith("#"):
            continue
        file_values[key] = value
    if remote_profile:
        file_values.update({key.removeprefix("REMOTE_"): value for key, value in list(file_values.items()) if key.startswith("REMOTE_")})
    for key, value in file_values.items():
        if key.startswith("REMOTE_") or key in os.environ:
            continue
        if not remote_profile and (not value or key in REMOTE_ONLY_KEYS or key.startswith(REMOTE_ONLY_PREFIXES)):
            continue
        os.environ[key] = value

# Local-friendly defaults so `fastapi dev` works without MySQL/Redis/MinIO/pgvector.
# Export these yourself, or set them in the env file, to override.
os.environ.setdefault("DODO_STORAGE_BACKEND", "sqlite")
os.environ.setdefault("DODO_FILE_STORAGE_BACKEND", "local")
os.environ.setdefault("DODO_REDIS_ENABLED", "false")
os.environ.setdefault("DODO_VECTOR_ENABLED", "false")

from python_backend.fastapi_app import app  # noqa: E402

__all__ = ["app"]

