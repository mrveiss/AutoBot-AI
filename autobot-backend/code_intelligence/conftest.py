# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Local pytest configuration for code_intelligence tests.

Issue #9856: The top-level conftest stubs code_intelligence and
code_intelligence.security_analyzer as MagicMocks to avoid importing the
heavy code_intelligence/__init__.py chain. That stub must be replaced with
the real modular package for security_analyzer_test.py to exercise actual
detection logic.

This conftest runs after autobot-backend/conftest.py (parent-first order)
and loads the real modules into sys.modules before any test in this
directory imports them.

NOTE (session-global side-effect): the sys.modules mutations below affect the
entire pytest session, not just tests inside code_intelligence/.  Any test
outside this directory that lazily imports a code_intelligence.security
submodule will exec the real (heavy) file rather than the top-level stub.
This is safe today because no such test exists, but be aware when adding new
test files that import code_intelligence.security indirectly.
"""

import importlib
import importlib.util
import logging
import sys
from pathlib import Path

_logger = logging.getLogger(__name__)

_backend_root = Path(__file__).parent.parent


def _load_real(module_name: str, file_path: Path) -> None:
    """Load a module from a real file, replacing any existing stub.

    Uses spec_from_file_location for leaf modules (non-package .py files).
    For __package__ correctness: leaf modules (foo.bar.baz -> __package__ =
    "foo.bar") use rpartition; package __init__.py files must use
    importlib.import_module so the normal machinery sets __package__ correctly
    to the package's own name and wires up submodule_search_locations.
    Do NOT call _load_real for package __init__.py files.
    """
    spec = importlib.util.spec_from_file_location(module_name, str(file_path))
    if spec is None or spec.loader is None:
        _logger.warning("_load_real: cannot build spec for %s at %s", module_name, file_path)
        return
    mod = importlib.util.module_from_spec(spec)
    # For a leaf module "a.b.c", __package__ = "a.b" (correct).
    # Never pass an __init__.py here — use importlib.import_module instead.
    mod.__package__ = module_name.rpartition(".")[0] or module_name
    sys.modules[module_name] = mod
    try:
        spec.loader.exec_module(mod)  # type: ignore[union-attr]
    except Exception as exc:
        sys.modules.pop(module_name, None)
        _logger.warning("_load_real: failed to exec %s: %s", module_name, exc)
        raise


# Repair the code_intelligence stub: give it a real __path__ so that
# sub-module imports resolve to real files on disk.  We deliberately do NOT
# exec code_intelligence/__init__.py (it drags in the full backend stack),
# but the stub's __path__ must point at the real directory so that
# `import code_intelligence.security.constants` finds the real .py file.
import types as _types

_ci_mod = sys.modules.get("code_intelligence")
if _ci_mod is None or not isinstance(_ci_mod, _types.ModuleType):
    _ci_mod = _types.ModuleType("code_intelligence")
_ci_mod.__path__ = [str(_backend_root / "code_intelligence")]
_ci_mod.__package__ = "code_intelligence"
if not hasattr(_ci_mod, "__spec__") or _ci_mod.__spec__ is None:
    _ci_mod.__spec__ = importlib.util.spec_from_file_location(
        "code_intelligence",
        str(_backend_root / "code_intelligence" / "__init__.py"),
    )
sys.modules["code_intelligence"] = _ci_mod

# Ensure the code_intelligence.security sub-package and all its sub-modules are
# real.  Remove any existing stubs (from the top-level conftest) so that normal
# import machinery can load the package from disk via _ci_mod.__path__.
#
# Rationale for using importlib.import_module (not _load_real) for the package:
# spec_from_file_location sets __package__ = rpartition(".")[0], which for the
# package name "code_intelligence.security" yields "code_intelligence" — wrong.
# A package __init__.py needs __package__ == its own dotted name so that its
# relative imports ("from .analyzer import ...") resolve correctly.  The normal
# import machinery (importlib.import_module) sets this correctly and also
# populates spec.submodule_search_locations so sub-imports keep working.
for _key in list(sys.modules.keys()):
    if _key == "code_intelligence.security" or _key.startswith("code_intelligence.security."):
        del sys.modules[_key]

importlib.import_module("code_intelligence.security")

# Replace the stub for the shim module with the real one.
_load_real(
    "code_intelligence.security_analyzer",
    _backend_root / "code_intelligence" / "security_analyzer.py",
)

# Expose the real security_analyzer on the code_intelligence namespace so that
# `from code_intelligence.security_analyzer import X` finds the real symbols.
_real_sa = sys.modules.get("code_intelligence.security_analyzer")
if _real_sa is not None:
    setattr(sys.modules["code_intelligence"], "security_analyzer", _real_sa)
