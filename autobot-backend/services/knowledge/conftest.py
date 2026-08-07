# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Restore the module stubs the knowledge service tests install at import time.

#13435: four test modules here — ``test_analyzer_service``,
``test_kb_synthesizer``, ``test_doc_indexer`` and
``test_doc_indexer_dim_mismatch`` — stub heavy dependencies before importing
their subject, because each loads its module through ``importlib`` to bypass
``services/knowledge/__init__.py``. Installing those stubs is necessary. What
was missing is the other half: nothing put ``sys.modules`` back, so ``utils``,
``utils.chromadb_client`` and ``utils.async_chromadb_client`` stayed stubbed for
every test collected afterwards in the same worker.

The consequences were real, and were previously patched at the far end instead
of here: ``utils/chromadb_auth_test.py`` and
``utils/chromadb_client_cache_key_test.py`` failed in CI while passing alone
(worked around in #13438), and ``services/rag_service_kb_synthesis_test.py``
still does (#13386). The `sys.modules` leak guard (#13361) now fails the run on
it, which is what surfaced this.

**Why this lives in conftest rather than in a helper the tests import.**
``pytest.ini`` sets ``--import-mode=importlib``, which does not put a test's own
directory on ``sys.path`` — a sibling module is therefore not importable from
these files (the same trap #13368 records for ``tools/codemods``). pytest does
load a directory's ``conftest.py`` before it imports the test modules beside it,
so this module runs first and can capture the pre-stub state without the four
files needing to change at all.

Restoration is package-scoped, not module-scoped: the four modules share
``utils`` and its children, so tearing down after the first would pull the stub
out from under the other three.
"""

from __future__ import annotations

import sys
from typing import Any, Dict

import pytest

# The names these four modules install via their own ``_make_stub`` helpers.
# Listed explicitly rather than diffed against a full ``sys.modules`` snapshot:
# a diff would also revert legitimate imports performed by tests that run in
# between, which is a much larger and less predictable blast radius.
_STUBBED_NAMES = (
    "autobot_shared.ssot_config",
    "utils",
    "utils.chromadb_client",
    "utils.async_chromadb_client",
    "constants",
    "constants.path_constants",
)

_MISSING = object()

# Captured at conftest import — before pytest imports the test modules in this
# directory, therefore before any of them installs a stub.
_PRE_STUB_STATE: Dict[str, Any] = {name: sys.modules.get(name, _MISSING) for name in _STUBBED_NAMES}

# ``utils.async_chromadb_client`` is also bound as an attribute on the ``utils``
# package so ``mock.patch("utils.async_chromadb_client....")`` can resolve it
# (#11532, #12463). Injecting into ``sys.modules`` alone does not do that, so
# the attribute has to be restored separately from the module entry.
_PRE_STUB_UTILS_ATTR: Any = (
    getattr(sys.modules["utils"], "async_chromadb_client", _MISSING) if "utils" in sys.modules else _MISSING
)


@pytest.fixture(scope="module", autouse=True)
def _reinstall_module_stubs(request):
    """Re-install a module's unloaded stubs for the duration of its own tests.

    A test module here unloads its stubs immediately after using them to import
    its subject (``_STUBS_UNLOADED_AFTER_IMPORT``), so nothing is left installed
    while pytest imports the rest of the session's modules — that import phase
    is when the leak was escaping. The stubs are still required *during* the
    module's tests, which patch dotted paths resolved through ``sys.modules``,
    so they go back in here and come out again straight afterwards.

    Module-scoped: each module owns exactly the names it unloaded, so two
    modules stubbing the same name cannot tear down each other's.
    """
    unloaded = getattr(request.module, "_STUBS_UNLOADED_AFTER_IMPORT", None)
    if not unloaded:
        yield
        return

    # What each name held before this fixture overwrote it (#13651). Popping
    # blindly on teardown destroyed a *genuine* module whenever an earlier test
    # in the session had already imported it for real: the key went absent, the
    # next importer built a second module object, and the leak guard reported
    # the swap as "replaced" — genuine displaced by genuine.
    displaced: Dict[str, Any] = {}
    restored_parent_attr = False
    for name, module in unloaded.items():
        displaced[name] = sys.modules.get(name, _MISSING)
        sys.modules[name] = module
        # Re-bind on the parent package too — patch() resolves "utils.x.Y" as
        # getattr(sys.modules["utils"], "x") (#11532, #12463).
        parent_name, _, leaf = name.rpartition(".")
        parent = sys.modules.get(parent_name) if parent_name else None
        if parent is not None:
            setattr(parent, leaf, module)
            restored_parent_attr = True

    yield

    for name in unloaded:
        previous = displaced[name]
        if previous is _MISSING:
            sys.modules.pop(name, None)
        else:
            sys.modules[name] = previous
        parent_name, _, leaf = name.rpartition(".")
        parent = sys.modules.get(parent_name) if parent_name else None
        if previous is not _MISSING and parent is not None:
            setattr(parent, leaf, previous)
        elif restored_parent_attr and parent is not None and hasattr(parent, leaf):
            delattr(parent, leaf)


@pytest.fixture(scope="package", autouse=True)
def _restore_knowledge_stubs():
    """Put the remaining import-time stubs back once this package is done.

    Covers the names the test modules still leave installed after import —
    ``autobot_shared.ssot_config``, ``utils``, ``constants`` and its child —
    which the leak guard's baseline does not list for this directory.
    """
    yield

    utils_mod = sys.modules.get("utils")
    if utils_mod is not None:
        if _PRE_STUB_UTILS_ATTR is _MISSING:
            if hasattr(utils_mod, "async_chromadb_client"):
                delattr(utils_mod, "async_chromadb_client")
        else:
            utils_mod.async_chromadb_client = _PRE_STUB_UTILS_ATTR

    for name in reversed(_STUBBED_NAMES):
        previous = _PRE_STUB_STATE[name]
        if previous is _MISSING:
            sys.modules.pop(name, None)
        else:
            sys.modules[name] = previous
