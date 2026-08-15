# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Make ``services`` a real package for the tests co-located inside it (#14286).

The slm-backend root conftest (#3499) stubs ``services`` as a MagicMock so the
``api/*`` tests import without heavy dependencies. ``tests/services/conftest.py``
(#11478) swaps that stub for a hollow ``ModuleType`` whose ``__path__`` points at
the real directory, so real submodules resolve.

Four test modules live *here*, next to the code, and import real submodules the
same way — ``inventory_builder_test``, ``a2a_card_fetcher_test``,
``hf_token_validator_test``, ``service_extra_data_test``. Nothing arranged that
for them. They passed only when something under ``tests/services/`` happened to
be collected first in the same process, which is decided by pytest-split's
shard composition — so adding or removing an unrelated test file elsewhere in
the repo could move them into a shard where ``services`` is still a MagicMock,
and every ``from services.x import y`` here silently yields a mock.

That is what it looks like: ``assert 'mynode-42' in <MagicMock name=
'mock.inventory_builder.build_registry_inventory()...>`` — an assertion failure
in a file the change never touched.

The fix-up is idempotent and returns immediately when ``services`` is already a
package, so this costs nothing when ``tests/services/`` did run first.
"""

import sys
import types
from pathlib import Path

_SLM_ROOT = Path(__file__).parent.parent


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
