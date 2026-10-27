"""FastAPI entrypoint for Hotline Agent.

Run:
  uv run fastapi dev
  uv run fastapi dev main.py --port 8888
  python -m uvicorn main:app --reload --port 8888
"""

from __future__ import annotations

from python_backend.bootstrap import load_environment

load_environment()

from python_backend.fastapi_app import app  # noqa: E402

__all__ = ["app"]


