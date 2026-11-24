"""Compatibility import; implementation lives in modules.skills.catalog."""
import sys
from importlib import import_module

if __name__ == '__main__':
    from pathlib import Path
    import runpy
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    runpy.run_module('python_backend.modules.skills.catalog', run_name='__main__')
else:
    sys.modules[__name__] = import_module("python_backend.modules.skills.catalog")
