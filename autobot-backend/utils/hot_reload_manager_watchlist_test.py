# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Every hot-reload watch entry must name a real importable module.

`chat_workflow_modules` entries are passed to `importlib.import_module()` and
used as `sys.modules` keys, so a name that does not resolve can never be
reloaded. `"src.async_chat_workflow"` was a leftover from the old `src/`
layout — `src/async_chat_workflow.py` does not exist, so the entry never
matched and that module was silently never hot-reloadable.

The failure mode is why this needs a test rather than a fix alone: nothing
reports it at startup. `reload_module()` only logs "Module ... not registered"
if someone happens to trigger a reload, and `register_module` accepts any
string, so a typo here is invisible until a developer wonders why their edits
are not taking effect.
"""

import importlib.util

import pytest

from utils.hot_reload_manager import HotReloadManager


def _watchlist():
    return HotReloadManager().chat_workflow_modules


def test_watchlist_is_not_empty():
    """A silently-emptied list would make this suite vacuously pass."""
    assert _watchlist(), "chat_workflow_modules is empty"


@pytest.mark.parametrize("module_name", _watchlist())
def test_watched_module_is_importable(module_name):
    """importlib.import_module() is called with this exact string."""
    try:
        spec = importlib.util.find_spec(module_name)
    except (ImportError, ModuleNotFoundError, ValueError):
        spec = None

    assert spec is not None, (
        f"hot-reload watches '{module_name}', which is not importable — "
        "it can never be reloaded, and nothing reports that at startup"
    )


@pytest.mark.parametrize("module_name", _watchlist())
def test_watched_module_has_no_stale_layout_prefix(module_name):
    """The backend root was once `src/`; entries must not carry that prefix."""
    assert not module_name.startswith("src."), (
        f"'{module_name}' uses the retired src/ layout prefix"
    )
