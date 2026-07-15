# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Conftest for tests/services/ — make real SLM packages importable (#11478).

The slm-backend root conftest (#3499) stubs ``services`` / ``models`` (and a
fixed list of their submodules) as MagicMocks so api/* tests import without
heavy dependencies.  A MagicMock is not a package — accessing ``__path__``
raises AttributeError — so any test here importing a real, non-stubbed
submodule (``services.inventory_builder``, …) failed with
"'services' is not a package", and the whole directory could not collect.

Fix: swap the PARENT stubs for hollow ``ModuleType`` packages whose
``__path__`` points at the real directories (the same trick the root conftest
uses for ``api``).  Existing per-submodule MagicMock stubs stay in
``sys.modules`` and keep winning for the stubbed names; only non-stubbed
submodules fall through to the real files.  Child stubs are re-bound as parent
attributes so ``patch("services.encryption.x")`` still resolves to the same
object as ``from services.encryption import x`` (#9780).

Also imports the real ``autobot_shared`` package up front so no test module
can squat the key with a bare (non-package) ``ModuleType`` stub — that squat
broke every later ``autobot_shared.*`` import in the directory sweep.
"""

import sys
import types
from pathlib import Path

_SLM_ROOT = Path(__file__).parent.parent.parent


def _ensure_real_pkg(name: str, directory: Path) -> None:
    """Replace a non-package sys.modules entry with a real-path hollow package."""
    existing = sys.modules.get(name)
    if existing is not None and hasattr(existing, "__path__"):
        return  # already a package (real or hollow)

    pkg = types.ModuleType(name)
    pkg.__path__ = [str(directory)]  # type: ignore[assignment]
    pkg.__package__ = name
    pkg.__spec__ = None  # type: ignore[assignment]

    # Re-bind existing child stubs onto the new parent (#9780).
    prefix = name + "."
    depth = name.count(".") + 1
    for key, child in list(sys.modules.items()):
        if key.startswith(prefix) and key.count(".") == depth:
            setattr(pkg, key.rsplit(".", 1)[1], child)

    sys.modules[name] = pkg


_ensure_real_pkg("services", _SLM_ROOT / "services")
_ensure_real_pkg("models", _SLM_ROOT / "models")

# Real packages up front — several test modules in this directory install
# module-level fallback stubs guarded by `if X not in sys.modules`.  Importing
# the real packages here makes those guards no-ops, so a bare (non-package)
# stub can never squat the key for every later module in the sweep
# (e.g. `import aiohttp.abc` → "'aiohttp' is not a package").
# NOTE: `fastapi` must NOT be pre-imported here — test_saml_slo deliberately
# stubs it before exec'ing api/auth.py (real FastAPI would validate routes
# against MagicMock response models at decoration time).
import contextlib

import autobot_shared  # noqa: E402,F401

with contextlib.suppress(ImportError):
    import aiohttp  # noqa: F401
