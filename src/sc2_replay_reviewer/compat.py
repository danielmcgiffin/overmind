"""Runtime compatibility for the unmaintained import hook used by s2protocol."""

from __future__ import annotations

import importlib.machinery
import importlib.util
import sys
import types


def install_s2protocol_compat() -> None:
    """Provide only the old ``imp`` functions s2protocol still calls.

    s2protocol's generated protocol modules are otherwise used unchanged. This
    can be removed once the dependency releases a Python 3.13-compatible
    versions loader.
    """

    if "imp" in sys.modules:
        return
    imp = types.ModuleType("imp")
    imp.PY_SOURCE = "PY_SOURCE"

    def find_module(name: str, path: list[str] | None = None):
        spec = importlib.machinery.PathFinder.find_spec(name, path)
        if spec is None or spec.origin is None:
            raise ImportError(name)
        return open(spec.origin, "rb"), spec.origin, (".py", "rb", imp.PY_SOURCE)

    def load_module(name: str, file_handle, path: str, description):
        spec = importlib.util.spec_from_file_location(name, path)
        if spec is None or spec.loader is None:
            raise ImportError(name)
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
        return module

    imp.find_module = find_module
    imp.load_module = load_module
    sys.modules["imp"] = imp
