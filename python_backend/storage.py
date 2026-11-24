"""Compatibility import; implementation lives in modules.storage.relational."""
import sys
from importlib import import_module

sys.modules[__name__] = import_module("python_backend.modules.storage.relational")
