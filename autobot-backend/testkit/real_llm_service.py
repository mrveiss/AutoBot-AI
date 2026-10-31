# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Load the genuine ``services/llm_service.py`` for a test (#19649).

The backend conftest keeps ``services.llm_service`` a deliberate stub (its Redis/NPU
import chain), so importing it by name yields a ``MagicMock`` surface with no real
``chat`` and ``create_autospec(LLMService)`` against it fails. Loading the file
privately leaves that stub in place for every other test.

Each call returns a **fresh** module, as each test file's own loader did before this
was shared: a test that sets module-level state does not leak it into another's copy.
A file that cannot load fails its test; it must not skip, or a criterion would read
as checked when it was not.
"""

import importlib.util
import itertools
import sys
from pathlib import Path
from types import ModuleType

_BACKEND = Path(__file__).resolve().parents[1]
_COPIES = itertools.count(1)
# Submodules llm_service imports that the conftest does not pre-load.
_PRELOADED = ("llm_shared.rate_limit_backoff", "llm_shared.fallback_events")


def _load(name: str, relpath: str) -> ModuleType:
    """Execute *relpath* (under ``autobot-backend``) as module *name*, registered in ``sys.modules``."""
    spec = importlib.util.spec_from_file_location(name, _BACKEND / relpath)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def load_real_llm_service() -> ModuleType:
    """A fresh copy of the real ``services/llm_service.py`` under a private name."""
    for public in _PRELOADED:
        if public not in sys.modules:
            _load(public, public.replace(".", "/") + ".py")
    return _load(f"_real_llm_service_{next(_COPIES)}", "services/llm_service.py")
