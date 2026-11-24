"""Compatibility import; implementation lives in modules.storage.objects."""
import sys
from importlib import import_module

sys.modules[__name__] = import_module("python_backend.modules.storage.objects")
