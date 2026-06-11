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
"""

import importlib
import importlib.util
import sys
from pathlib import Path

_backend_root = Path(__file__).parent.parent


def _load_real(module_name: str, file_path: Path) -> None:
    """Load a module from a real file, replacing any existing stub."""
    spec = importlib.util.spec_from_file_location(module_name, str(file_path))
    if spec is None or spec.loader is None:
        return
    mod = importlib.util.module_from_spec(spec)
    mod.__package__ = module_name.rpartition(".")[0] or module_name
    sys.modules[module_name] = mod
    try:
        spec.loader.exec_module(mod)  # type: ignore[union-attr]
    except Exception:
        sys.modules.pop(module_name, None)


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

# Ensure the code_intelligence.security sub-package and its modules are real.
# Load leaf modules first so that each parent's __init__ can import them.

_security_root = _backend_root / "code_intelligence" / "security"

# Register the security package namespace first so sub-module loads succeed.
_sec_pkg = _types.ModuleType("code_intelligence.security")
_sec_pkg.__path__ = [str(_security_root)]
_sec_pkg.__package__ = "code_intelligence.security"
sys.modules["code_intelligence.security"] = _sec_pkg

for _name, _rel in [
    ("code_intelligence.security.constants", "constants.py"),
    ("code_intelligence.security.finding", "finding.py"),
    ("code_intelligence.security.patterns", "patterns.py"),
    ("code_intelligence.security.ast_visitor", "ast_visitor.py"),
    ("code_intelligence.security.analyzer", "analyzer.py"),
    ("code_intelligence.security.utils", "utils.py"),
]:
    _load_real(_name, _security_root / _rel)

# Reload the security package __init__ now that all sub-modules are present.
_load_real("code_intelligence.security", _security_root / "__init__.py")

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
