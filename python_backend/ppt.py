"""Compatibility import; implementation lives in modules.documents.ppt."""
import sys
from importlib import import_module

sys.modules[__name__] = import_module("python_backend.modules.documents.ppt")
