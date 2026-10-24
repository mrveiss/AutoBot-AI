# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Repo-wide pytest plugin: a test that replaces the SSOT config singleton puts it back.

``ssot_config.get_config()`` is an ``lru_cache(maxsize=1)`` singleton. Tests that
need fresh env-derived values clear it (``get_config.cache_clear()``,
``reload_config()``), and until now nothing restored it. Every object bound to the
OLD instance at import time then disagrees with the proxy for the rest of the
process -- ``models/settings.py``'s section aliases (``llm_settings = config.llm``)
are the reported case: ``settings_test.py`` failed 6 or 7 cases whenever it ran
after ``redis_host_ssot_fallback_14299_test.py``, on base and on #19232.

The rule: whatever instance the cache held before a test is what it holds after.

* held one before -> re-seeded with that same instance after (not an equal copy:
  import-time bindings compare by identity);
* held none before -> cleared after, so a test's env-shaped instance never leaks;
* ``importlib.reload(ssot_config)`` (``ssot_config_test.py`` does it to re-run
  import-time parsing) rebinds every global in place -- a new ``config`` proxy, a new
  ``get_config`` -- so the module's namespace is put back as it was, too.

Only engages when ``autobot_shared.ssot_config`` is already imported; it never
imports it, so suites that stub or avoid it are untouched.
"""

from __future__ import annotations

import sys
from typing import Any, Iterator
from unittest.mock import patch

import pytest

_MODULE = "autobot_shared.ssot_config"


def _cached_instance(module: Any) -> Any:
    """The instance the singleton cache holds now, or None (never constructs one)."""
    return module.get_config() if module.get_config.cache_info().currsize else None


def restore_singleton(module: Any, original: Any) -> None:
    """Make *module*'s singleton cache hold *original* again (None: hold nothing)."""
    module.get_config.cache_clear()
    if original is None:
        return
    # get_config() constructs through the module-global AutoBotConfig at call time, so
    # one call with that name bound to the saved instance re-seeds the cache with it.
    with patch.object(module, "AutoBotConfig", lambda: original):
        module.get_config()


#: The module namespace as first seen, per module object -- copied ONCE, not per test, and
#: used only if a test reloads the module in place.
_FIRST_NAMESPACE: dict[int, dict[str, Any]] = {}


def _first_namespace(module: Any) -> dict[str, Any]:
    """The namespace *module* had when this plugin first saw it."""
    return _FIRST_NAMESPACE.setdefault(id(module), dict(module.__dict__))


@pytest.fixture(autouse=True)
def _ssot_config_singleton_restored() -> Iterator[None]:
    """Costs two identity reads and a cache-size read per test; acts only when ssot_config changed."""
    module = sys.modules.get(_MODULE)
    if module is None or not hasattr(module, "get_config"):
        yield
        return
    namespace = _first_namespace(module)
    get_config, original = module.get_config, _cached_instance(module)
    yield
    if sys.modules.get(_MODULE) is not module:
        return  # the test removed or replaced the module object; nothing of ours to restore
    if module.get_config is not get_config:
        module.__dict__.clear()
        module.__dict__.update(namespace)  # undo an in-place reload
    if _cached_instance(module) is not original:
        restore_singleton(module, original)
