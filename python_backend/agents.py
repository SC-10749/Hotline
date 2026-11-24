"""Compatibility import; implementation lives in modules.execution.engine."""
import sys
from importlib import import_module

sys.modules[__name__] = import_module("python_backend.modules.execution.engine")
