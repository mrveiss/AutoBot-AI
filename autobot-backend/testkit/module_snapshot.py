# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Reload a module for one test without leaving the reload behind (#19878).

``importlib.reload`` re-executes the module in place: every class and constant is a
new object, and a test module that bound the old class at import time then fails
``isinstance`` against the new one. Undoing the env var that drove the reload does not
undo the reload, so a later test in the same worker sees whatever the reload produced.
``reloaded`` snapshots the module namespace and puts it back on exit.
"""

import importlib
from contextlib import contextmanager
from types import ModuleType
from typing import Iterator


@contextmanager
def reloaded(module: ModuleType) -> Iterator[ModuleType]:
    """Yield *module* re-executed; on exit restore its original namespace objects."""
    saved = dict(vars(module))
    try:
        yield importlib.reload(module)
    finally:
        vars(module).clear()
        vars(module).update(saved)
